"""DeepSeek transport, reusing the core request/logging/tool execution loop."""

import copy
import json
import os
import re

from odoo import _
from odoo.exceptions import UserError
from odoo.addons.ai.utils.ai_logging import api_call_logging
from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai.utils.llm_providers import PROVIDERS


# Compatibility identifiers for agents created before model discovery existed.
# These are not offered in a fresh database unless the API lists them.
LEGACY_DEEPSEEK_MODEL_NAMES = frozenset(("deepseek-chat", "deepseek-reasoner"))


class DeepSeekLLMApiService(LLMApiService):
    """A separate service class; core classes and provider lists stay untouched."""

    def __init__(self, env, provider="deepseek"):
        if provider != "deepseek":
            raise ValueError("DeepSeekLLMApiService only supports the deepseek provider")
        self.env = env
        self.provider = provider
        self.base_url = "https://api.deepseek.com/v1"

    def _get_api_token(self):
        token = self.env["ir.config_parameter"].sudo().get_param("ai.deepseek_key")
        token = token or os.getenv("ODOO_AI_DEEPSEEK_TOKEN")
        if not token:
            raise UserError(_("No API key set for provider '%s'", self.provider))
        return token

    def list_models(self):
        """Discover text models, validating the complete response before caching it."""
        payload = self._request("get", "/models", self._get_base_headers(), None, timeout=10)
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or not entries:
            raise UserError(_("DeepSeek returned an empty or invalid model list."))
        reserved = {name for provider in PROVIDERS for name, _label in provider.llms}
        models, seen = [], set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise UserError(_("DeepSeek returned an invalid model entry."))
            model_id = entry.get("id")
            if (not isinstance(model_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", model_id)
                    or model_id in seen or model_id in reserved):
                raise UserError(_("DeepSeek returned an invalid or conflicting model identifier."))
            seen.add(model_id)
            compatible = True
            for key in ("input_modalities", "output_modalities"):
                modalities = entry.get(key)
                if modalities is not None:
                    if not isinstance(modalities, list) or not all(isinstance(item, str) for item in modalities):
                        raise UserError(_("DeepSeek returned invalid model capabilities."))
                    compatible = compatible and "text" in modalities
            if not compatible:
                continue
            name = entry.get("name") or model_id
            if not isinstance(name, str) or len(name) > 300:
                raise UserError(_("DeepSeek returned an invalid model name."))
            models.append({"id": model_id, "name": name.strip() or model_id})
        if not models:
            raise UserError(_("DeepSeek did not return any compatible text models."))
        return models

    def _request_llm(
        self, llm_model, system_prompts, user_prompts, tools=None,
        files=None, schema=None, temperature=0.2, inputs=(), web_grounding=False,
    ):
        if files:
            raise UserError(_("The DeepSeek connector currently supports text messages, not file inputs."))
        if schema:
            raise UserError(_("The DeepSeek connector does not support structured response schemas."))
        if web_grounding:
            raise UserError(_("The DeepSeek connector does not support web grounding."))

        messages = [{"role": "system", "content": prompt} for prompt in system_prompts]
        messages.extend(copy.deepcopy(item) for item in inputs or ()
                        if item.get("role") in ("system", "user", "assistant", "tool"))
        messages.extend({"role": "user", "content": prompt} for prompt in user_prompts)
        body = {"model": llm_model, "messages": messages}
        # Reasoning models may reject or ignore sampling controls.
        if llm_model not in ("deepseek-reasoner",):
            # Native Odoo chat history stores role/content, not reasoning_content.
            # Explicit non-thinking mode supports consecutive visitor turns with tools.
            body["thinking"] = {"type": "disabled"}
            body["temperature"] = temperature
        if tools:
            body["tools"] = [{
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameter_schema,
                },
            } for name, (description, _allow_end, _callback, parameter_schema) in tools.items()]
            body["tool_choice"] = "auto"

        with api_call_logging(messages, tools) as record_response:
            payload = self._request("post", "/chat/completions", self._get_base_headers(), body)
            choices = payload.get("choices") if isinstance(payload, dict) else None
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise UserError(_("DeepSeek returned an invalid response. Please try again."))
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise UserError(_("DeepSeek returned an invalid message. Please try again."))
            if choices[0].get("finish_reason") == "length":
                raise UserError(_("DeepSeek could not finish this response. Please use a shorter request."))

            responses = [message["content"]] if message.get("content") else []
            calls = []
            next_inputs = list(inputs or ())
            tool_calls = message.get("tool_calls") or []
            if not isinstance(tool_calls, list):
                raise UserError(_("DeepSeek returned invalid tool calls. No tools from this response were run."))
            # Validate the entire model response before handing any calls to core.
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    raise UserError(_("DeepSeek returned an invalid tool call."))
                function = tool_call.get("function") or {}
                if not isinstance(function, dict):
                    raise UserError(_("DeepSeek returned an invalid tool function."))
                name = function.get("name")
                call_id = tool_call.get("id")
                if name not in (tools or {}):
                    raise UserError(_("DeepSeek requested a tool that is not available to this agent."))
                if not isinstance(call_id, str) or not call_id:
                    raise UserError(_("DeepSeek returned a tool call without a valid identifier."))
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except (TypeError, json.JSONDecodeError) as error:
                    raise UserError(_("DeepSeek returned invalid JSON tool arguments.")) from error
                if not isinstance(arguments, dict):
                    raise UserError(_("DeepSeek tool arguments must be a JSON object."))
                calls.append((name, call_id, arguments))
            if calls:
                # Retain reasoning_content when supplied, including for Reasoner.
                next_inputs.append(message)
            if record_response:
                record_response(calls, responses)
            return responses, calls, next_inputs

    def _build_tool_call_response(self, tool_call_id, return_value):
        return {"role": "tool", "tool_call_id": tool_call_id, "content": str(return_value)}

    def get_embedding(self, *args, **kwargs):
        raise UserError(_("This DeepSeek connector supports chat and tools only, not embeddings or knowledge sources."))

    def get_transcription(self, *args, **kwargs):
        raise UserError(_("This DeepSeek connector does not support audio transcription."))

    def get_transcription_session(self, *args, **kwargs):
        raise UserError(_("This DeepSeek connector does not support realtime audio sessions."))
