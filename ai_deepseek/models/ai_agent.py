from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.ai.models.ai_agent import TEMPERATURE_MAP

from ..services.deepseek_api_service import DeepSeekLLMApiService
from ..services.model_catalog import DeepSeekModelCatalog


class AIAgent(models.Model):
    _inherit = "ai.agent"

    # Core uses a function object. Rebind to a method name so inheritance applies.
    # selection_add cannot extend a callable Selection in Odoo 19.
    llm_model = fields.Selection(selection="_get_llm_model_selection")

    @api.model
    def _get_llm_model_selection(self):
        choices = super()._get_llm_model_selection()
        existing = {name for name, _label in choices}
        return choices + [item for item in DeepSeekModelCatalog(self.env).get_selection()
                          if item[0] not in existing]

    @api.model_create_multi
    def create(self, vals_list):
        default_model = self.default_get(["llm_model"]).get("llm_model")
        self._validate_discovered_model_values([
            {"llm_model": vals.get("llm_model", default_model)} for vals in vals_list
        ])
        return super().create(vals_list)

    def write(self, vals):
        # An existing retired model remains editable; no automatic model switch.
        if "llm_model" in vals and any(agent.llm_model != vals["llm_model"] for agent in self):
            self._validate_discovered_model_values([vals])
        return super().write(vals)

    @api.model
    def _validate_discovered_model_values(self, vals_list):
        requested = {vals["llm_model"] for vals in vals_list if vals.get("llm_model")}
        if requested - dict(self._get_llm_model_selection()).keys():
            raise ValidationError(_("Choose an available model. Refresh DeepSeek models in AI Settings if needed."))

    @api.model
    def _cron_refresh_deepseek_models(self):
        return DeepSeekModelCatalog(self.env).refresh()

    def _get_provider(self):
        self.ensure_one()
        if self.llm_model in DeepSeekModelCatalog(self.env).get_model_ids():
            return "deepseek"
        return super()._get_provider()

    def _get_embedding_model(self):
        self.ensure_one()
        if self.llm_model in DeepSeekModelCatalog(self.env).get_model_ids():
            self._check_deepseek_sources()
            # Core write() calls this even if the agent has no sources.
            # Do not register a nonexistent deepseek-embed model globally.
            return False
        return super()._get_embedding_model()

    @api.constrains("llm_model", "sources_ids")
    def _check_deepseek_sources(self):
        model_ids = DeepSeekModelCatalog(self.env).get_model_ids()
        if any(agent.llm_model in model_ids and agent.sources_ids for agent in self):
            raise ValidationError(_(
                "DeepSeek agents currently support text and business tools only. "
                "Remove this agent's knowledge sources or choose a model with a supported embedding provider."
            ))

    def _generate_response(self, prompt, chat_history=None, extra_system_context=""):
        self.ensure_one()
        if self.llm_model not in DeepSeekModelCatalog(self.env).get_model_ids():
            return super()._generate_response(prompt, chat_history, extra_system_context)
        self._check_deepseek_sources()
        return DeepSeekLLMApiService(self.env).request_llm(
            self.llm_model,
            self._build_system_context(extra_system_context=extra_system_context),
            [],
            inputs=(chat_history or []) + [{"role": "user", "content": prompt}],
            tools=self.topic_ids.tool_ids._get_ai_tools(),
            temperature=TEMPERATURE_MAP[self.response_style],
        )
