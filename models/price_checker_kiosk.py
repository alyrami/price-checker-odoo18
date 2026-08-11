# -*- coding: utf-8 -*-

import ipaddress
import uuid

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PriceCheckerKiosk(models.Model):
    """
    One record per physical tablet/kiosk device running the public,
    unauthenticated Track B price-checker page.

    Access to this model is intentionally restricted to the dedicated
    `group_kiosk_admin` group only (see security/price_checker_security.xml
    and security/ir.model.access.csv) — not to stock.group_stock_manager,
    not to System Administrator, and not to any other existing role. This
    was Rami's explicit decision on 2026-08-10 (see SPRINT_BACKLOG.md Task 7).
    Public/portal users have zero ORM access to this model; the public
    controller routes only ever reach it via sudo() to resolve a token,
    read-only (see controllers/price_checker_controller.py).
    """

    _name = 'price_checker.kiosk'
    _description = 'Price Checker Kiosk Device'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(required=True, help="Friendly label for this device, e.g. \"Front Counter Tablet\".")

    token = fields.Char(
        required=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid.uuid4()),
        help="Unguessable token embedded in this kiosk's public URL "
             "(/price_checker/kiosk/<token>). Treat it like a secret: anyone "
             "with the URL can use this kiosk. Not directly editable from the "
             "form — use the Regenerate action if it may have leaked.",
    )

    # Deliberately NO default here (B7 / Task 7 acceptance criteria): a kiosk
    # must always be scoped to one explicit company, and creating one without
    # picking a company must fail validation rather than silently falling
    # back to env.company or "the first company".
    company_id = fields.Many2one(
        'res.company',
        required=True,
        string='Company',
        help="Company this kiosk's product lookups are scoped to. The public "
             "lookup route resolves company_id ONLY from this field — never "
             "from the requester's session, IP, or any other signal.",
    )

    active = fields.Boolean(default=True)

    rate_limit_per_minute = fields.Integer(
        default=25,
        required=True,
        help="Maximum public lookup requests per minute this kiosk's token "
             "may make (defense in depth — see Task 10). Sane default is "
             "20-30/min for a single busy tablet.",
    )

    allowed_ip_cidr = fields.Char(
        string='Allowed IP / CIDR',
        help="Optional. e.g. 192.168.1.0/24. When set, public requests for "
             "this kiosk are rejected unless they originate from this range "
             "(defense in depth only — see Task 11). Leave blank to skip "
             "this check entirely.",
    )

    kiosk_url = fields.Char(
        string='Public Kiosk URL',
        compute='_compute_kiosk_url',
        help="Full public URL for this kiosk. Open this on the tablet, or "
             "generate a QR code from it.",
    )

    _sql_constraints = [
        ('token_unique', 'unique(token)', 'This kiosk token is already in use — tokens must be unique.'),
    ]

    @api.depends('token')
    def _compute_kiosk_url(self):
        # sudo() is safe here: web.base.url is a non-sensitive system setting
        # (the instance's own base URL) and this only ever reads it, never
        # writes; group_kiosk_admin members otherwise have no reason to be
        # granted direct access to ir.config_parameter.
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for kiosk in self:
            kiosk.kiosk_url = (
                f"{base_url}/price_checker/kiosk/{kiosk.token}" if kiosk.token else False
            )

    @api.constrains('rate_limit_per_minute')
    def _check_rate_limit_per_minute(self):
        for kiosk in self:
            if kiosk.rate_limit_per_minute <= 0:
                raise ValidationError("Rate limit per minute must be a positive number.")

    @api.constrains('allowed_ip_cidr')
    def _check_allowed_ip_cidr(self):
        for kiosk in self:
            if kiosk.allowed_ip_cidr:
                try:
                    ipaddress.ip_network(kiosk.allowed_ip_cidr, strict=False)
                except ValueError:
                    raise ValidationError(
                        "Allowed IP / CIDR must be a valid network, e.g. 192.168.1.0/24."
                    )

    def action_regenerate_token(self):
        """
        Replace this kiosk's token with a fresh, unguessable UUID.

        A dedicated action (rather than making the field freely editable) so
        staff can't accidentally fat-finger a predictable/reused token in —
        the token is effectively this kiosk's only access control, so it is
        either machine-generated or explicitly regenerated, never typed in.
        """
        for kiosk in self:
            kiosk.token = str(uuid.uuid4())
        return True
