{
    "name": "Flous Flow Smart Inventory Count",
    "version": "20.0.1.0.34",
    "category": "Inventory/Inventory",
    "summary": "Controlled multi-user physical inventory counts",
    "description": """Controlled physical inventory counting with employee sheets,
consolidation, variance review, and safe standard Odoo inventory adjustments.""",
    "author": "Flous Flow",
    "license": "LGPL-3",
    "images": [
        "static/description/cover.png",
        "static/description/workflow.png",
        "static/description/accounting.png",
    ],
    "depends": ["stock", "stock_account", "account", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "data/ir_sequence.xml",
        "data/stock_restrictions.xml",
        "views/inventory_count_views.xml",
        "views/inventory_count_settings.xml",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ff_smart_inventory_count/static/src/js/count_sheet_keyboard.js",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
