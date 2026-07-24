# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class PriceCheckerController(http.Controller):
    """
    Lightweight JSON-RPC endpoints consumed by the POS price-checker popup.
    POS runs in an isolated JS context so it cannot use the standard ORM service
    directly — these controllers bridge that gap.
    
    ENHANCEMENTS:
    - Calculates prices using ONLY sales taxes (type_tax_use='sale')
    - Excludes purchase taxes to show accurate customer-facing prices
    - This ensures the price displayed matches what customers will actually pay
    - Stock qty is scoped to the CURRENT company's warehouses only
      (fixes multi-company/branch setups returning cross-company stock)
    """

    # ------------------------------------------------------------------
    # /web/price_checker/search_by_barcode
    # Called when the cashier scans a barcode inside the POS popup.
    # ------------------------------------------------------------------
    @http.route(
        '/web/price_checker/search_by_barcode',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def search_by_barcode(self, barcode=None, **kw):
        """
        Search product.product (not template) by barcode.
        Returns a single dict or None.
        """
        try:
            if not barcode:
                return {'error': 'barcode is required'}

            # Search on product.product first (variant-level barcode),
            # fall back to product.template barcode.
            Product = request.env['product.product']
            products = Product.sudo().search(
                [('barcode', '=', barcode.strip()), ('active', '=', True)],
                limit=1
            )

            if not products:
                # Try on template level
                Template = request.env['product.template']
                templates = Template.sudo().search(
                    [('barcode', '=', barcode.strip()), ('active', '=', True)],
                    limit=1
                )
                if templates:
                    # Pick the first variant of that template
                    products = templates[0].product_variant_ids[:1]

            if not products:
                return {'product': None}

            return {'product': self._serialize_product(products[0])}
        
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error in search_by_barcode for barcode '{barcode}': {str(e)}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'product': None}

    # ------------------------------------------------------------------
    # /web/price_checker/get_product
    # Called when the POS already knows the product.product id
    # (e.g. user tapped a product in the order list).
    # ------------------------------------------------------------------
    @http.route(
        '/web/price_checker/get_product',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def get_product(self, product_id=None, **kw):
        if not product_id:
            return {'error': 'product_id is required'}

        product = request.env['product.product'].sudo().browse(int(product_id))
        if not product.exists() or not product.active:
            return {'product': None}

        return {'product': self._serialize_product(product)}

    # ------------------------------------------------------------------
    # /web/price_checker/search_by_name
    # Free-text search used by the POS popup's search input.
    # ------------------------------------------------------------------
    @http.route(
        '/web/price_checker/search_by_name',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def search_by_name(self, query=None, limit=10, **kw):
        try:
            if not query:
                return {'products': []}

            Product = request.env['product.product']
            products = Product.sudo().search(
                [
                    ('active', '=', True),
                    ('available_in_pos', '=', True),
                    '|', '|',
                    ('name', 'ilike', query.strip()),
                    ('default_code', 'ilike', query.strip()),
                    ('barcode', 'ilike', query.strip()),
                ],
                limit=int(limit)
            )

            return {'products': [self._serialize_product(p) for p in products]}
        
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error in search_by_name for query '{query}': {str(e)}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'products': []}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _get_company_stock_qty(self, product):
        """
        Return qty_available scoped to the CURRENT company's internal locations.

        Odoo's default qty_available aggregates stock across every company and
        branch the sudo context can see.  To restrict it to the active company
        we look up all internal stock.location records that belong to warehouses
        owned by the current company, then sum stock.quant rows for only those
        locations.

        Falls back to product.qty_available if stock.quant is not installed or
        something goes wrong (e.g. no warehouses configured yet).
        """
        try:
            company = request.env.company  # the company the user is currently in

            # Find all internal locations that belong to this company's warehouses
            Location = request.env['stock.location'].sudo()
            internal_locations = Location.search([
                ('usage', '=', 'internal'),
                ('company_id', '=', company.id),
            ])

            if not internal_locations:
                # No warehouse locations configured for this company yet — safe fallback
                return product.qty_available or 0.0

            location_ids = internal_locations.ids

            # Sum stock.quant for this product restricted to those locations
            Quant = request.env['stock.quant'].sudo()
            quants = Quant.search([
                ('product_id', '=', product.id),
                ('location_id', 'in', location_ids),
            ])
            qty = sum(quants.mapped('quantity')) - sum(quants.mapped('reserved_quantity'))
            return max(qty, 0.0)

        except Exception:
            # If stock module quirks arise, fall back gracefully
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "price_checker: could not compute company-scoped stock for "
                "product %s, falling back to qty_available", product.id, exc_info=True
            )
            return product.qty_available or 0.0

    def _serialize_product(self, product):
        """
        Build a flat dict with everything the POS popup needs.
        Runs under sudo (already called with sudo on the recordset).
        """
        try:
            template = product.product_tmpl_id

            # ── price with tax ────────────────────────────────────────────
            list_price = product.list_price or 0.0
            price_with_tax = list_price
            tax_amount = 0.0

            # Filter only SALES taxes (customer taxes, type_tax_use='sale')
            # Exclude purchase taxes to show accurate customer-facing prices
            taxes = product.taxes_id
            sales_taxes = taxes.filtered(lambda t: t.type_tax_use == 'sale')
            if sales_taxes:
                tax_data = sales_taxes.compute_all(
                    list_price,
                    currency=product.currency_id,
                    quantity=1.0,
                    product=product,
                    partner=None,
                )
                price_with_tax = tax_data.get('total_included', list_price)
                tax_amount = price_with_tax - tax_data.get('total_excluded', list_price)
            else:
                # No sales taxes, price with tax equals list price
                price_with_tax = list_price
                tax_amount = 0.0

            # ── stock (current company only) ──────────────────────────────
            # Uses _get_company_stock_qty() instead of product.qty_available so
            # that only warehouses/locations belonging to the active company are
            # considered — fixing cross-company stock aggregation in multi-
            # company / multi-branch setups.
            qty = self._get_company_stock_qty(product)
            if qty <= 0:
                stock_status = 'out_of_stock'
            elif qty <= 5:
                stock_status = 'low_stock'
            else:
                stock_status = 'in_stock'

            # ── image (base-64, small thumbnail) ──────────────────────────
            image_b64 = None
            raw_image = template.image_128
            if raw_image:
                if isinstance(raw_image, bytes):
                    image_b64 = raw_image.decode('ascii')
                else:
                    image_b64 = raw_image  # already a string in some Odoo versions

            # ── currency symbol ───────────────────────────────────────────
            currency_name = product.currency_id.name if product.currency_id else 'USD'
            currency_symbol = product.currency_id.symbol if product.currency_id else '$'

            return {
                'id': product.id,
                'template_id': template.id,
                'name': product.name or '',
                'barcode': product.barcode or '',
                'default_code': product.default_code or '',
                'categ_name': template.categ_id.complete_name if template.categ_id else '',
                'uom_name': product.uom_id.name if product.uom_id else '',
                # prices
                'list_price': round(list_price, 2),
                'price_with_tax': round(price_with_tax, 2),
                'tax_amount': round(tax_amount, 2),
                'currency_name': currency_name,
                'currency_symbol': currency_symbol,
                # stock (scoped to current company)
                'qty_available': round(qty, 2),
                'stock_status': stock_status,   # 'in_stock' | 'low_stock' | 'out_of_stock'
                # image
                'image_128': image_b64,
            }
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error serializing product {product.id}: {str(e)}", exc_info=True)
            # Return a minimal safe product dict
            return {
                'id': product.id,
                'template_id': product.product_tmpl_id.id if product.product_tmpl_id else 0,
                'name': product.name or 'Unknown Product',
                'barcode': product.barcode or '',
                'default_code': product.default_code or '',
                'categ_name': '',
                'uom_name': '',
                'list_price': 0.0,
                'price_with_tax': 0.0,
                'tax_amount': 0.0,
                'currency_name': 'USD',
                'currency_symbol': '$',
                'qty_available': 0.0,
                'stock_status': 'out_of_stock',
                'image_128': None,
                'error': str(e)
            }
