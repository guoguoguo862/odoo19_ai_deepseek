from odoo import api, models


class AIAgentSource(models.Model):
    _inherit = "ai.agent.source"

    @api.constrains("agent_id")
    def _check_deepseek_agent(self):
        self.agent_id._check_deepseek_sources()
