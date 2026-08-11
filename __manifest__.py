# -*- coding: utf-8 -*-
{
    'name': 'Price Checker',
    'version': '18.0.3.3.0',
    'category': 'Point of Sale',
    'summary': 'Enhanced price & stock checker with native barcode scanner integration',
    'description': """
        Price Checker
        =============
        Quick product-price & stock lookup from the backend (Inventory menu),
        from inside the Odoo 18 Point-of-Sale interface, and from a public,
        no-login kiosk tablet page.
        Features
        --------
        * Integrated with Odoo's native BarcodeReader service for seamless hardware scanner support
        * Camera-based barcode scanning (native BarcodeDetector, vendored ZXing fallback)
          in the backend Barcode Scanner screen
        * Optional public kiosk tablet page (per-device, tokenized URL) for
          customer self-service price checks: name, image, and price only —
          no login, no stock/cost/internal data ever exposed
        * Smart tax calculation: shows sales price with only sales taxes (customer-facing)
        * Excludes purchase taxes from customer price display for accuracy
        * Company-scoped stock: available quantity shows only the current company's stock,
          so multi-company / multi-branch setups never see stock leaking across branches
        * Barcode scanner support (hardware + manual) in both backend & POS
        * Price with tax & tax-amount breakdown
        * Real-time on-hand stock status (In Stock / Low Stock / Out of Stock)
        * Product image preview
        * Audio feedback on scan success / failure
        * POS: dedicated "Price Checker" button in the control panel
        * POS: full-screen interface with search and scan capabilities
        * Bilingual-ready (Arabic / English)

        Changelog
        ---------
        * 18.0.3.3.0 (2026-08-10): Camera barcode scanning added. Backend Barcode
          Scanner screen gets a "Scan with Camera" button (Track A). New, separate
          public kiosk tablet page at /price_checker/kiosk/<token> for customer
          self-service price checks (Track B) — new price_checker.kiosk model,
          new dedicated "Kiosk Administrator" security group (not System
          Administrator, not Inventory/Stock Manager), per-kiosk rate limiting
          and optional IP allowlist. No changes to pricing/tax logic, POS
          integration, or the existing three staff-facing lookup routes.
    """,
    'author': 'Rami-Aly',
    'support': 'ramielaly@gmail.com',
    'license': 'OPL-1',
    'price': 25.00,
    'currency': 'USD',
    'depends': [
        'base',
        'product',
        'stock',
        'barcodes',
        'account',
        'point_of_sale',
    ],
    'data': [
        # security/price_checker_security.xml must load before
        # ir.model.access.csv, which references its group_kiosk_admin id.
        'security/price_checker_security.xml',
        'security/ir.model.access.csv',
        'views/price_checker_views.xml',
        'views/price_checker_barcode_views.xml',
        'views/price_checker_kiosk_views.xml',
        'views/price_checker_kiosk_public_templates.xml',
        'views/price_checker_menu.xml',
    ],
    # NOTE (Track B camera-scanning sprint, Task 3):
    # This module vendors ZXing locally at static/lib/zxing/zxing-library.js
    # (MIT license, see static/lib/zxing/LICENSE.txt) for the ZXing-fallback
    # decode path used when the browser has no native BarcodeDetector API.
    # It is intentionally NOT listed in any bundle below: Odoo core itself
    # treats its own equivalent vendored copy the same way (present only in
    # its test-only bundle, never in 'web.assets_backend'). Loading it
    # unconditionally on every backend page (or on the kiosk page) for every
    # user, most of whom will never need it, would be unnecessary weight and
    # conflicts with the brief's "not loaded unconditionally" requirement.
    # static/src/js/camera_barcode_scanner.js lazy-loads it on demand, by
    # its own static URL, only when BarcodeDetector is unavailable.
    'assets': {
        'web.assets_backend': [
            # Load order: shared engine -> Owl camera dialog -> existing
            # backend Barcode Scanner screen (which now opens that dialog).
            'alyrami_price_checker/static/src/js/camera_barcode_scanner.js',
            'alyrami_price_checker/static/src/js/camera_scanner_dialog.js',
            'alyrami_price_checker/static/src/xml/camera_scanner_dialog.xml',
            'alyrami_price_checker/static/src/js/barcode_scanner.js',
            'alyrami_price_checker/static/src/xml/barcode_scanner.xml',
        ],
        'point_of_sale._assets_pos': [
            'alyrami_price_checker/static/src/css/pos_price_checker.css',
            'alyrami_price_checker/static/src/js/pos_price_checker.js',
            'alyrami_price_checker/static/src/xml/pos_price_checker.xml',
        ],
        # TRACK B — Task 14: isolated bundle for the public kiosk page ONLY.
        # CSS only. The two JS files (camera_barcode_scanner.js,
        # kiosk_price_checker.js) are deliberately NOT listed here — Odoo's
        # asset bundler wraps every JS file it processes in an odoo.define(...)
        # call regardless of the @odoo-module tag, which throws
        # "odoo is not defined" on this page since it never loads Odoo's module
        # loader (by design). They're served as plain <script src="..."> tags
        # directly from views/price_checker_kiosk_public_templates.xml instead,
        # bypassing the bundler entirely. See that file's comments for detail.
        #
        # Referenced exclusively from views/price_checker_kiosk_public_templates.xml
        # via t-call-assets. Deliberately NOT included in web.assets_backend,
        # point_of_sale._assets_pos, or any other authenticated/POS bundle —
        # a user who never opens the kiosk URL never loads any of this.
        'alyrami_price_checker.assets_kiosk': [
            'alyrami_price_checker/static/src/css/kiosk_price_checker.css',
        ],
    },
    'images': [
        'static/description/banner.png',
        'static/description/screenshot_backend.png',
        'static/description/screenshot_pos_popup.png',
        'static/description/screenshot_pos_menu.png',
        'static/description/screenshot_product_list.png',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}

