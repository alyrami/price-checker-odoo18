# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ── computed fields (unchanged from v1) ──────────────────────────────
    price_checker_stock_status = fields.Selection([
        ('in_stock', 'In Stock'),
        ('out_of_stock', 'Out of Stock'),
        ('low_stock', 'Low Stock'),
    ], string='Stock Status', compute='_compute_price_checker_stock_status', store=False)

    price_checker_price_with_tax = fields.Float(
        string='Price with Tax',
        compute='_compute_price_with_tax',
        store=False
    )

    price_checker_tax_amount = fields.Float(
        string='Tax Amount',
        compute='_compute_price_with_tax',
        store=False
    )

    def _get_company_qty_available(self):
        """
        Return qty_available restricted to the CURRENT company's internal
        stock locations only.

        Odoo's standard qty_available (virtual_available) aggregates across
        every company and branch visible under sudo.  In a multi-company /
        multi-branch setup this inflates the number shown in the price checker.

        We fix it by querying stock.quant filtered to locations whose
        company_id matches the active company.
        """
        self.ensure_one()
        company = self.env.company
        Location = self.env['stock.location'].sudo()
        internal_locs = Location.search([
            ('usage', '=', 'internal'),
            ('company_id', '=', company.id),
        ])
        if not internal_locs:
            # Fallback: no warehouses configured for this company yet
            return self.qty_available or 0.0

        Quant = self.env['stock.quant'].sudo()
        # product.template may have multiple variants — sum all of them
        variant_ids = self.product_variant_ids.ids
        if not variant_ids:
            return 0.0

        quants = Quant.search([
            ('product_id', 'in', variant_ids),
            ('location_id', 'in', internal_locs.ids),
        ])
        qty = sum(quants.mapped('quantity')) - sum(quants.mapped('reserved_quantity'))
        return max(qty, 0.0)

    @api.depends('qty_available')
    def _compute_price_checker_stock_status(self):
        for product in self:
            try:
                qty = product._get_company_qty_available()
            except Exception:
                qty = product.qty_available or 0.0

            if qty <= 0:
                product.price_checker_stock_status = 'out_of_stock'
            elif qty <= 5:
                product.price_checker_stock_status = 'low_stock'
            else:
                product.price_checker_stock_status = 'in_stock'

    @api.depends('list_price', 'taxes_id')
    def _compute_price_with_tax(self):
        """
        Compute price with tax using ONLY sales taxes (customer taxes).
        Purchase taxes are excluded to show accurate customer-facing prices.
        """
        for product in self:
            # Filter only sales taxes (type_tax_use='sale')
            sales_taxes = product.taxes_id.filtered(lambda t: t.type_tax_use == 'sale')
            
            if sales_taxes:
                taxes = sales_taxes.compute_all(
                    product.list_price,
                    currency=product.currency_id,
                    quantity=1.0,
                    product=product,
                    partner=None
                )
                product.price_checker_price_with_tax = taxes['total_included']
                product.price_checker_tax_amount = taxes['total_included'] - taxes['total_excluded']
            else:
                # No sales taxes, price with tax equals list price
                product.price_checker_price_with_tax = product.list_price
                product.price_checker_tax_amount = 0.0
