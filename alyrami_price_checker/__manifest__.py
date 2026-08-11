# -*- coding: utf-8 -*-
{
    'name': 'Price Checker',
    'version': '18.0.3.2.2',
    'category': 'Point of Sale',
    'summary': 'Enhanced price & stock checker with native barcode scanner integration',
    'description': """
        Price Checker
        =============
        Quick product-price & stock lookup from the backend (Inventory menu)
        and from inside the Odoo 18 Point-of-Sale interface.
        Features
        --------
        * Integrated with Odoo's native BarcodeReader service for seamless hardware scanner support
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
        'security/ir.model.access.csv',
        'views/price_checker_views.xml',
        'views/price_checker_barcode_views.xml',
        'views/price_checker_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'alyrami_price_checker/static/src/js/barcode_scanner.js',
            'alyrami_price_checker/static/src/xml/barcode_scanner.xml',
        ],
        'point_of_sale._assets_pos': [
            'alyrami_price_checker/static/src/css/pos_price_checker.css',
            'alyrami_price_checker/static/src/js/pos_price_checker.js',
            'alyrami_price_checker/static/src/xml/pos_price_checker.xml',
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

