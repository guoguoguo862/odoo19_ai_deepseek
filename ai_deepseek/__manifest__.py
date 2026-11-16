{
    "name": "AI DeepSeek Provider",
    "version": "19.0.1.1.0",
    "category": "Productivity/AI",
    "summary": "DeepSeek chat and business tools for Odoo AI agents",
    "author": "Suto",
    "license": "LGPL-3",
    "depends": ["ai_app"],
    "data": ["views/res_config_settings_views.xml", "data/ir_cron.xml"],
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "application": False,
    "installable": True,
}
