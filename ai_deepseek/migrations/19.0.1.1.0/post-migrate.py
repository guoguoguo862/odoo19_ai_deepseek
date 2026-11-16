from odoo import SUPERUSER_ID, api
from odoo.addons.ai_deepseek.services.model_catalog import DeepSeekModelCatalog


def migrate(cr, version):
    DeepSeekModelCatalog(api.Environment(cr, SUPERUSER_ID, {})).refresh()
