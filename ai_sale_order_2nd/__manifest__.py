# -*- coding: utf-8 -*-
{
    "name": "AI Sale Order Assistant",
    "version": "19.0.1.0.0",
    "category": "Sales",
    "summary": "Create draft sale orders through Odoo AI assistant tools",
    "author": "Suto",
    "license": "LGPL-3",
    "depends": [
        "ai_app",
        "sale",
        "website_sale",
        "website_livechat",
        "ai_livechat",
        "ai_website_livechat",
    ],
    "data": [
        "data/ai_sale_order_tool_data.xml",
    ],
    "application": False,
    "installable": True,
}
