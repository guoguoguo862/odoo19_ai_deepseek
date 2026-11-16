"""Per-database model discovery. Selection reads never perform network requests."""

import json
import logging

from odoo import _, fields
from odoo.exceptions import UserError

from .deepseek_api_service import DeepSeekLLMApiService, LEGACY_DEEPSEEK_MODEL_NAMES


_logger = logging.getLogger(__name__)
CATALOG_PARAMETER = "ai.deepseek_models"


class DeepSeekModelCatalog:
    def __init__(self, env):
        self.env = env

    def get_state(self):
        raw = self.env["ir.config_parameter"].sudo().get_param(CATALOG_PARAMETER, "{}")
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(state, dict):
            return {}
        models = state.get("models", [])
        known = state.get("known", {})
        if (not isinstance(models, list) or not isinstance(known, dict)
                or any(not isinstance(item, dict)
                       or not isinstance(item.get("id"), str)
                       or not isinstance(item.get("name"), str) for item in models)
                or any(not isinstance(key, str) or not isinstance(value, str)
                       for key, value in known.items())):
            return {}
        return state

    def get_models(self):
        return self.get_state().get("models", [])

    def get_model_ids(self):
        state = self.get_state()
        return (set(state.get("known", {}))
                | {item["id"] for item in state.get("models", [])}
                | LEGACY_DEEPSEEK_MODEL_NAMES)

    def get_selection(self):
        state = self.get_state()
        current = {item["id"]: item["name"] for item in state.get("models", [])}
        choices = [(model_id, self._label(model_id, name)) for model_id, name in current.items()]
        known = state.get("known", {})
        retired = (set(known) | LEGACY_DEEPSEEK_MODEL_NAMES) - set(current)
        if retired:
            agents = self.env["ai.agent"].sudo().with_context(active_test=False).search([
                ("llm_model", "in", sorted(retired)),
            ])
            for model_id in sorted(set(agents.mapped("llm_model"))):
                label = self._label(model_id, known.get(model_id, model_id))
                choices.append((model_id, _("%s (not in current catalog)", label)))
        return choices

    @staticmethod
    def _label(model_id, name):
        return name if "deepseek" in name.lower() else "DeepSeek: %s" % name

    def refresh(self):
        """Keep the last successful directory on credential/network/format failures."""
        state = self.get_state()
        attempt = fields.Datetime.to_string(fields.Datetime.now())
        service = DeepSeekLLMApiService(self.env)
        try:
            service._get_api_token()
        except UserError:
            return self._failed(state, attempt, "missing_key", _(
                "Configure a DeepSeek API key, then save or refresh the model list."
            ))
        try:
            models = service.list_models()
        except (UserError, ValueError):
            # Do not persist raw HTTP errors, which can contain remote response data.
            _logger.warning("DeepSeek model discovery failed; keeping the previous catalog.")
            return self._failed(state, attempt, "error", _(
                "Could not refresh DeepSeek models. The previous list was kept. "
                "Check the API key and network connection, then retry."
            ))
        known = dict(state.get("known", {}))
        known.update({item["id"]: item["name"] for item in state.get("models", [])})
        known.update({item["id"]: item["name"] for item in models})
        message = _("Loaded %s DeepSeek models.", len(models))
        self._save({
            "models": models, "known": known,
            "last_success": attempt, "last_attempt": attempt,
            "status": "ok", "message": message,
        })
        return {"ok": True, "message": message, "count": len(models)}

    def _failed(self, state, attempt, status, message):
        state.update(last_attempt=attempt, status=status, message=message)
        self._save(state)
        return {"ok": False, "message": message, "count": len(state.get("models", []))}

    def _save(self, state):
        self.env["ir.config_parameter"].sudo().set_param(
            CATALOG_PARAMETER, json.dumps(state, ensure_ascii=False),
        )
