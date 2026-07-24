# -*- coding: utf-8 -*-
{
    'name': 'Price Checker',
    'version': '18.0.3.2.1',
    'category': 'Point of Sale',
    'summary': 'Enhanced price & stock checker with native barcode scanner integration',
    'description': """
        Price Checker Module v3.2.1 - COMPANY-SCOPED STOCK FIX
        =======================================================
        Quick product-price & stock lookup from the backend (Inventory menu)
        **and** from inside the Odoo 18 Point-of-Sale interface.

        Features
        --------
        * **Integrated with Odoo's native BarcodeReader service** for seamless hardware scanner support
        * **Smart tax calculation**: Shows sales price with ONLY sales taxes (customer-facing)
        * **Excludes purchase taxes** from customer price display for accuracy
        * **Company-scoped stock**: Available qty now shows ONLY the current company's stock
          (fixes multi-company/branch setups where all branches' stock was aggregated)
        * Barcode scanner support (hardware + manual) in both backend & POS
        * Price with tax & tax-amount breakdown
        * Real-time on-hand stock status (In Stock / Low Stock / Out of Stock)
        * Product image preview
        * Audio feedback on scan success / failure
        * POS: dedicated "Price Checker" button in the control panel
        * POS: full-screen interface with search and scan capabilities
        * Bilingual-ready (Arabic / English)
        
        v3.2.1 Fix
        ----------
        * FIXED: Available qty was aggregating stock from ALL companies and branches.
          Now only stock in internal locations belonging to the active company is counted.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'product',
        'stock',
        'barcodes',
        'account',
        'point_of_sale',          # ← NEW: POS integration
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/price_checker_views.xml',
        'views/price_checker_barcode_views.xml',
        'views/price_checker_menu.xml',
    ],
    'assets': {
        # ── backend barcode scanner (unchanged) ──────────────────────────
        'web.assets_backend': [
            'price_checker/static/src/js/barcode_scanner.js',
            'price_checker/static/src/xml/barcode_scanner.xml',
        ],
        # ── POS assets ────────────────────────────────────────────────────
        'point_of_sale._assets_pos': [
            'price_checker/static/src/css/pos_price_checker.css',
            'price_checker/static/src/js/pos_price_checker.js',
            'price_checker/static/src/xml/pos_price_checker.xml',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
