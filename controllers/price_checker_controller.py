# -*- coding: utf-8 -*-

import ipaddress
import logging
import threading
import time

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# TRACK B — module-level, in-process rate-limit state for the public kiosk
# lookup route (Task 10). Keyed by (kiosk token, requester IP).
#
# KNOWN LIMITATION (documented per Task 10's brief — accepted, not a v1
# blocker): this is plain in-memory Python state, scoped to a single worker
# process. It does NOT survive a server restart and is NOT shared across
# multiple Odoo worker processes/threads. On a multi-worker deployment the
# *effective* ceiling is therefore roughly (per-worker limit x worker
# count), not one strict global limit. This is acceptable because the
# primary defenses on this route are exact-match-only search + the
# minimal-fields serializer (B12/B3), not this counter — see the "Accepted
# risk" section of SPRINT_BACKLOG.md.
# ----------------------------------------------------------------------
_KIOSK_RATE_LIMIT_LOCK = threading.Lock()
_KIOSK_RATE_LIMIT_BUCKETS = {}
_KIOSK_RATE_LIMIT_WINDOW_SECONDS = 60


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
    - Product lookups are scoped to the CURRENT company (or company-agnostic
      products) so a user in one company cannot look up products that belong
      exclusively to another company.
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

            company_domain = self._company_domain()

            # Search on product.product first (variant-level barcode),
            # fall back to product.template barcode.
            Product = request.env['product.product']
            products = Product.sudo().search(
                company_domain + [('barcode', '=', barcode.strip()), ('active', '=', True)],
                limit=1
            )

            if not products:
                # Try on template level
                Template = request.env['product.template']
                templates = Template.sudo().search(
                    company_domain + [('barcode', '=', barcode.strip()), ('active', '=', True)],
                    limit=1
                )
                if templates:
                    # Pick the first variant of that template
                    products = templates[0].product_variant_ids[:1]

            if not products:
                return {'product': None}

            return {'product': self._serialize_product(products[0])}

        except Exception:
            _logger.error(
                "Error in search_by_barcode for barcode '%s'", barcode, exc_info=True
            )
            return {'error': 'Server error while searching by barcode', 'product': None}

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
        try:
            if not product_id:
                return {'error': 'product_id is required'}

            try:
                product_id = int(product_id)
            except (TypeError, ValueError):
                return {'error': 'product_id must be an integer'}

            company_domain = self._company_domain()
            product = request.env['product.product'].sudo().search(
                company_domain + [('id', '=', product_id), ('active', '=', True)],
                limit=1
            )
            if not product:
                return {'product': None}

            return {'product': self._serialize_product(product)}

        except Exception:
            _logger.error(
                "Error in get_product for product_id '%s'", product_id, exc_info=True
            )
            return {'error': 'Server error while fetching product', 'product': None}

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

            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = 10
            # Never let the client request an unbounded/oversized result set.
            limit = max(1, min(limit, 50))

            Product = request.env['product.product']
            products = Product.sudo().search(
                self._company_domain() + [
                    ('active', '=', True),
                    ('available_in_pos', '=', True),
                    '|', '|',
                    ('name', 'ilike', query.strip()),
                    ('default_code', 'ilike', query.strip()),
                    ('barcode', 'ilike', query.strip()),
                ],
                limit=limit
            )

            return {'products': [self._serialize_product(p) for p in products]}

        except Exception:
            _logger.error(
                "Error in search_by_name for query '%s'", query, exc_info=True
            )
            return {'error': 'Server error while searching by name', 'products': []}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _company_domain(self):
        """
        Domain restricting product searches to the current company.

        Products with no company_id set (company_id = False) are shared
        across all companies, so they remain visible everywhere. Products
        tied to a specific company are only visible to users operating in
        that company. Without this, .sudo() searches would ignore Odoo's
        normal multi-company record rules and leak products (and their
        prices/stock) across companies.
        """
        company = request.env.company
        return ['|', ('company_id', '=', False), ('company_id', '=', company.id)]

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
        except Exception:
            _logger.error("Error serializing product %s", product.id, exc_info=True)
            # Return a minimal safe product dict — never expose exception details to the client.
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
                'error': 'Server error while formatting product data',
            }

    # ==================================================================
    # TRACK B — public, unauthenticated kiosk routes (Tasks 9-12).
    #
    # Everything below this line is ADDITIVE ONLY. Nothing above this line
    # (search_by_barcode, get_product, search_by_name, _serialize_product,
    # _company_domain, _get_company_stock_qty) is touched by Track B — those
    # remain the staff/POS-facing, auth='user' surface, byte-for-byte
    # unchanged (B11).
    #
    # SECURITY — these routes run with auth='public': no login, no session,
    # and a hostile caller can call them directly with any input, bypassing
    # the kiosk page's UI entirely. Every rule below exists because of that:
    #   - Only _serialize_public_product() is ever returned here — never
    #     _serialize_product() (B1, B3, B10, B11).
    #   - company_id is resolved ONLY from the price_checker.kiosk record
    #     matched by token — never from request/session/env.company, and
    #     never "first company" (B7).
    #   - Barcode matching is exact (`=`) only — no ilike, no name search,
    #     no fallback (B12).
    #   - Zero .write(/.create(/.unlink( calls anywhere below (B13).
    # ==================================================================

    def _get_active_kiosk(self, token):
        """
        Resolve a price_checker.kiosk record from its public URL token.

        Returns an empty recordset (falsy) for a missing/unknown token or an
        archived (active=False) kiosk — callers must treat all of those
        identically (generic "not found", B8: never confirm to a caller
        whether a given token exists).

        Runs under sudo() solely because auth='public' callers have (by
        design, see security/ir.model.access.csv) zero ORM access to this
        model. The result is used strictly read-only, only to learn which
        single company + rate limit + IP allowlist apply to this request.
        """
        if not token:
            return request.env['price_checker.kiosk']
        return request.env['price_checker.kiosk'].sudo().search([
            ('token', '=', token),
            ('active', '=', True),
        ], limit=1)

    def _kiosk_request_ip(self):
        """
        Best-effort requester IP for rate limiting / IP allowlisting.

        Uses werkzeug's remote_addr, which Odoo's own --proxy-mode setting
        (ProxyFix) already corrects for a trusted reverse proxy in front of
        the instance. We deliberately do NOT read X-Forwarded-For directly
        here ourselves, since a raw client-supplied header would be trivial
        to spoof unless already sanitized by proxy-mode/ProxyFix.
        """
        return request.httprequest.remote_addr

    def _kiosk_ip_allowed(self, kiosk, ip):
        """
        Task 11 — optional local-network IP allowlist, defense in depth only.

        Primary controls remain exact-match-only search + minimal-fields
        serialization + rate limiting; this is one extra layer, not the
        sole control (B8's "where feasible" framing).

        Blank allowed_ip_cidr => check skipped entirely (opt-in per kiosk,
        unchanged behavior). A configured-but-invalid CIDR fails CLOSED
        (rejects) rather than silently ignoring the intended restriction.
        """
        if not kiosk.allowed_ip_cidr:
            return True
        if not ip:
            return False
        try:
            network = ipaddress.ip_network(kiosk.allowed_ip_cidr, strict=False)
            return ipaddress.ip_address(ip) in network
        except ValueError:
            _logger.warning(
                "price_checker kiosk: kiosk '%s' has an invalid allowed_ip_cidr "
                "value; failing closed (rejecting) until it is corrected.",
                kiosk.id,
            )
            return False

    def _kiosk_rate_limited(self, kiosk, ip):
        """
        Task 10 — in-memory sliding-window rate limit, keyed per kiosk token
        + requester IP, enforcing kiosk.rate_limit_per_minute (default 25,
        i.e. within the brief's ~20-30/min guidance). Limit is per-kiosk, so
        one busy store's tablet can never throttle another store's kiosk.

        See the module-level _KIOSK_RATE_LIMIT_* comment above for the
        documented in-memory/single-worker limitation.
        """
        limit = kiosk.rate_limit_per_minute or 25
        key = (kiosk.token, ip or 'unknown')
        now = time.monotonic()
        with _KIOSK_RATE_LIMIT_LOCK:
            bucket = _KIOSK_RATE_LIMIT_BUCKETS.setdefault(key, [])
            cutoff = now - _KIOSK_RATE_LIMIT_WINDOW_SECONDS
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= limit:
                return True
            bucket.append(now)
            return False

    def _serialize_public_product(self, product):
        """
        Task 9 — minimal, kiosk-safe product dict for the public Track B
        surface. Returns ONLY name / image_128 / price / currency — nothing
        else, ever (B1, B3, B10). Deliberately does NOT call or reuse
        _serialize_product() above, which returns stock quantities,
        category, internal reference, and other fields that must never
        reach an unauthenticated caller (B11).

        Uses the same sales-tax-only computation _serialize_product() uses,
        recomputed independently here rather than shared, so this method
        has no code path that could ever return more than these four keys.
        """
        list_price = product.list_price or 0.0
        price_with_tax = list_price

        sales_taxes = product.taxes_id.filtered(lambda t: t.type_tax_use == 'sale')
        if sales_taxes:
            tax_data = sales_taxes.compute_all(
                list_price,
                currency=product.currency_id,
                quantity=1.0,
                product=product,
                partner=None,
            )
            price_with_tax = tax_data.get('total_included', list_price)

        template = product.product_tmpl_id
        image_b64 = None
        raw_image = template.image_128
        if raw_image:
            image_b64 = raw_image.decode('ascii') if isinstance(raw_image, bytes) else raw_image

        currency_name = product.currency_id.name if product.currency_id else 'USD'
        currency_symbol = product.currency_id.symbol if product.currency_id else '$'

        # Exactly these four keys. Do not add to this dict without going
        # back through the brief's council-agent review (B1/B3/B10).
        return {
            'name': product.name or '',
            'image_128': image_b64,
            'price': round(price_with_tax, 2),
            'currency': currency_symbol or currency_name,
        }

    def _kiosk_product_lookup(self, kiosk, barcode):
        """
        Task 9 — exact-barcode-match-only product search, scoped strictly to
        the resolved kiosk's company. No ilike, no free-text fallback, no
        name-search logic of any kind (B12).
        """
        barcode = (barcode or '').strip()
        if not barcode:
            return None

        # Shared (company_id=False) products remain visible everywhere, same
        # semantics as the staff-facing _company_domain(); company-specific
        # products are scoped strictly to kiosk.company_id — never any other
        # company, never env.company (B7).
        domain = [
            '|', ('company_id', '=', False), ('company_id', '=', kiosk.company_id.id),
            ('barcode', '=', barcode),
            ('active', '=', True),
        ]

        # sudo() is required here: auth='public' callers have no ORM access to
        # product.product/product.template at all (no such grant exists for
        # base.group_public/base.group_portal), so a plain search would
        # always return empty. It is safe specifically because this method's
        # only two callers (kiosk_lookup, indirectly) always pass the result
        # straight into _serialize_public_product(), which hard-codes its
        # output to exactly 4 fields — sudo() here can never widen what the
        # caller ultimately receives.
        Product = request.env['product.product'].sudo()
        products = Product.search(domain, limit=1)

        if not products:
            Template = request.env['product.template'].sudo()
            templates = Template.search(domain, limit=1)
            if templates:
                products = templates[0].product_variant_ids[:1]

        return products[0] if products else None

    @http.route(
        '/price_checker/kiosk/<string:token>/lookup',
        type='json',
        auth='public',
        methods=['POST'],
    )
    def kiosk_lookup(self, token, barcode=None, **kw):
        """
        Task 9/10/11 — public, read-only, exact-barcode-match lookup for a
        single kiosk device. Always returns a generic-shaped dict; never
        lets an exception escape as an HTTP 500 with a traceback, and never
        distinguishes "no such kiosk" from "kiosk is inactive" from
        "IP not allowed" in its response (B8).
        """
        try:
            kiosk = self._get_active_kiosk(token)
            if not kiosk:
                return {'error': 'Not found', 'product': None}

            ip = self._kiosk_request_ip()

            # Task 11 — optional IP allowlist (defense in depth).
            if not self._kiosk_ip_allowed(kiosk, ip):
                _logger.warning(
                    "price_checker kiosk: lookup blocked by IP allowlist (kiosk id=%s, ip=%s)",
                    kiosk.id, ip,
                )
                return {'error': 'Not found', 'product': None}

            # Task 10 — per-kiosk rate limit.
            if self._kiosk_rate_limited(kiosk, ip):
                _logger.warning(
                    "price_checker kiosk: rate limit exceeded (kiosk id=%s, ip=%s, limit=%s/min)",
                    kiosk.id, ip, kiosk.rate_limit_per_minute,
                )
                return {'error': 'Too many requests, please try again shortly', 'product': None}

            if not barcode or not str(barcode).strip():
                return {'error': 'barcode is required', 'product': None}

            product = self._kiosk_product_lookup(kiosk, str(barcode))
            if not product:
                return {'product': None}

            return {'product': self._serialize_public_product(product)}

        except Exception:
            _logger.error("Error in kiosk_lookup for token '%s'", token, exc_info=True)
            return {'error': 'Server error', 'product': None}

    @http.route(
        '/price_checker/kiosk/<string:token>',
        type='http',
        auth='public',
        methods=['GET'],
    )
    def kiosk_page(self, token, **kw):
        """
        Task 12 — public kiosk page shell. Resolves the kiosk the same way
        as kiosk_lookup (same not-found/inactive/IP-blocked handling, same
        refusal to confirm which case applies), then renders a minimal,
        self-contained page with no Odoo backend menu bar, no login prompt,
        and no dependency on any authenticated or POS session (B1, B6).
        """
        kiosk = self._get_active_kiosk(token)
        if not kiosk:
            return request.not_found()

        ip = self._kiosk_request_ip()
        if not self._kiosk_ip_allowed(kiosk, ip):
            _logger.warning(
                "price_checker kiosk: page request blocked by IP allowlist (kiosk id=%s, ip=%s)",
                kiosk.id, ip,
            )
            return request.not_found()

        return request.render('alyrami_price_checker.kiosk_public_page', {
            'kiosk_token': kiosk.token,
        })
