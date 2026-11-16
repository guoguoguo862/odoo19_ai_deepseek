import json
from unittest.mock import Mock, patch

from odoo import Command
from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai.utils.llm_providers import PROVIDERS
from odoo.addons.ai_deepseek.hooks import uninstall_hook
from odoo.addons.ai_deepseek.services.deepseek_api_service import DeepSeekLLMApiService
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDeepSeekIntegration(TransactionCase):
    """Exercise the addon against the unmodified core service and ORM models."""

    def setUp(self):
        super().setUp()
        self.parameters = self.env["ir.config_parameter"].sudo()
        # A regression run must never consume or expose the customer's real token.
        self.parameters.set_param("ai.deepseek_key", "test-deepseek-token")
        # Legacy protocol tests use a directory returned by a mocked provider.
        self.parameters.set_param("ai.deepseek_models", json.dumps({"models": [
            {"id": "deepseek-chat", "name": "DeepSeek Chat"},
            {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner"},
        ]}))
        self.service = DeepSeekLLMApiService(self.env)
        self.agent = self.env["ai.agent"].create({
            "name": "DeepSeek regression agent",
            "llm_model": "deepseek-chat",
            "system_prompt": "Use the supplied tools and report their actual results.",
        })

    @staticmethod
    def _reply(content=None, tool_calls=None):
        message = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return {"choices": [{"message": message}]}

    @staticmethod
    def _tool_call(name, arguments, call_id="call-1"):
        return {
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments),
            },
        }

    def test_models_are_added_only_by_the_installed_extension(self):
        selection = dict(self.env["ai.agent"]._fields["llm_model"]._description_selection(self.env))
        self.assertIn("deepseek-chat", selection)
        self.assertIn("deepseek-reasoner", selection)
        self.assertIn("gpt-4o", selection)
        self.assertIn("gemini-2.5-flash", selection)
        self.assertEqual(self.agent._get_provider(), "deepseek")
        # Mutating this process-global list would leak support to other databases.
        self.assertNotIn("deepseek", [provider.name for provider in PROVIDERS])
        with self.assertRaises(NotImplementedError):
            LLMApiService(self.env, provider="deepseek")

    def test_existing_model_provider_and_embedding_are_unchanged(self):
        self.agent.llm_model = "gpt-4o"
        self.assertEqual(self.agent._get_provider(), "openai")
        self.assertEqual(self.agent._get_embedding_model(), "text-embedding-3-small")
        self.agent.llm_model = "deepseek-chat"
        self.assertEqual(self.agent._get_provider(), "deepseek")
        self.assertFalse(self.agent._get_embedding_model())

    def test_service_uses_deepseek_endpoint_and_database_token_first(self):
        self.assertEqual(self.service.provider, "deepseek")
        self.assertEqual(self.service.base_url, "https://api.deepseek.com/v1")
        with patch.dict("os.environ", {"ODOO_AI_DEEPSEEK_TOKEN": "test-environment-token"}):
            self.assertEqual(self.service._get_api_token(), "test-deepseek-token")

    def test_token_falls_back_to_environment_and_missing_token_is_explicit(self):
        self.parameters.set_param("ai.deepseek_key", False)
        with patch.dict("os.environ", {"ODOO_AI_DEEPSEEK_TOKEN": "test-environment-token"}):
            self.assertEqual(self.service._get_api_token(), "test-environment-token")
        with patch.dict("os.environ", {"ODOO_AI_DEEPSEEK_TOKEN": ""}):
            with self.assertRaises(UserError):
                self.service._get_api_token()

    def test_text_request_keeps_history_and_sends_current_prompt_once(self):
        history = [{"role": "user", "content": "Earlier question"},
                   {"role": "assistant", "content": "Earlier answer"}]
        with patch.object(DeepSeekLLMApiService, "_request", return_value=self._reply("Found it.")) as request:
            answers = self.service.request_llm(
                "deepseek-chat", ["Catalog assistant"], [],
                inputs=history + [{"role": "user", "content": "Current question"}],
            )
        self.assertEqual(answers, ["Found it."])
        request.assert_called_once()
        method, endpoint, headers, body = request.call_args.args
        self.assertEqual((method, endpoint), ("post", "/chat/completions"))
        self.assertEqual(headers["Authorization"], "Bearer test-deepseek-token")
        self.assertEqual(body["model"], "deepseek-chat")
        self.assertEqual(body["messages"], [{"role": "system", "content": "Catalog assistant"}]
                         + history + [{"role": "user", "content": "Current question"}])

    def test_tool_round_trip_uses_core_loop_and_reports_actual_result(self):
        executed = []

        def add_product(arguments):
            executed.append(arguments)
            return {"reference": "TEST-SKU", "added_qty": 1}, None

        tools = {
            "add_product": (
                "Add one resolved catalog product", False, add_product,
                {"type": "object", "properties": {"reference": {"type": "string"}},
                 "required": ["reference"]},
            ),
        }
        responses = [self._reply(tool_calls=[self._tool_call("add_product", {"reference": "TEST-SKU"})]),
                     self._reply("One item was added.")]
        with patch.object(DeepSeekLLMApiService, "_request", side_effect=responses) as request:
            answers = self.service.request_llm(
                "deepseek-chat", ["Use actual catalog results"], ["Add one item"], tools=tools,
            )
        self.assertEqual(executed, [{"reference": "TEST-SKU"}])
        self.assertEqual(answers, ["One item was added."])
        self.assertEqual(request.call_count, 2)
        first_body = request.call_args_list[0].args[3]
        self.assertEqual(first_body["tool_choice"], "auto")
        self.assertEqual(first_body["tools"][0]["function"]["name"], "add_product")
        second_body = request.call_args_list[1].args[3]
        tool_messages = [message for message in second_body["messages"] if message["role"] == "tool"]
        self.assertEqual(tool_messages, [{
            "role": "tool", "tool_call_id": "call-1",
            "content": str({"reference": "TEST-SKU", "added_qty": 1}),
        }])

    def test_unknown_tool_is_rejected_without_execution(self):
        callback = Mock(return_value=("done", None))
        tools = {"allowed_tool": ("Allowed tool", False, callback,
                                  {"type": "object", "properties": {}, "required": []})}
        response = self._reply(tool_calls=[self._tool_call("unlisted_tool", {})])
        with patch.object(DeepSeekLLMApiService, "_request", return_value=response):
            with self.assertRaises(UserError):
                self.service.request_llm("deepseek-chat", [], ["Do it"], tools=tools)
        callback.assert_not_called()

    def test_malformed_tool_arguments_are_rejected_without_execution(self):
        callback = Mock(return_value=("done", None))
        tools = {"allowed_tool": ("Allowed tool", False, callback,
                                  {"type": "object", "properties": {}, "required": []})}
        call = self._tool_call("allowed_tool", {})
        call["function"]["arguments"] = "{invalid JSON"
        with patch.object(DeepSeekLLMApiService, "_request", return_value=self._reply(tool_calls=[call])):
            with self.assertRaises(UserError):
                self.service.request_llm("deepseek-chat", [], ["Do it"], tools=tools)
        callback.assert_not_called()

    def test_whole_model_tool_batch_is_validated_before_any_tool_runs(self):
        callback = Mock(return_value=("done", None))
        tools = {"allowed_tool": ("Allowed tool", False, callback,
                                  {"type": "object", "properties": {}, "required": []})}
        calls = [self._tool_call("allowed_tool", {}, "first"),
                 self._tool_call("allowed_tool", [], "second")]
        with patch.object(DeepSeekLLMApiService, "_request", return_value=self._reply(tool_calls=calls)):
            with self.assertRaises(UserError):
                self.service.request_llm("deepseek-chat", [], ["Do it"], tools=tools)
        callback.assert_not_called()

    def test_unsupported_features_fail_before_a_network_request(self):
        cases = [
            {"files": [{"mimetype": "application/pdf", "value": "unused"}]},
            {"schema": {"type": "object", "properties": {}}},
            {"web_grounding": True},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with patch.object(DeepSeekLLMApiService, "_request") as request:
                    with self.assertRaises(UserError):
                        self.service.request_llm("deepseek-chat", [], ["Question"], **arguments)
                request.assert_not_called()

    def test_reasoner_preserves_reasoning_content_and_omits_temperature(self):
        callback = Mock(return_value=("actual tool result", None))
        tools = {"allowed_tool": ("Allowed tool", False, callback,
                                  {"type": "object", "properties": {}, "required": []})}
        response = self._reply(tool_calls=[self._tool_call("allowed_tool", {})])
        response["choices"][0]["message"]["reasoning_content"] = "Tool selection reasoning"
        with patch.object(DeepSeekLLMApiService, "_request", side_effect=[response, self._reply("Done")]) as request:
            self.service.request_llm("deepseek-reasoner", [], ["Use the tool"], tools=tools)
        self.assertNotIn("temperature", request.call_args_list[0].args[3])
        messages = request.call_args_list[1].args[3]["messages"]
        assistant = next(message for message in messages if message["role"] == "assistant")
        self.assertEqual(assistant["reasoning_content"], "Tool selection reasoning")

    def test_invalid_response_and_non_object_arguments_fail_without_execution(self):
        callback = Mock(return_value=("done", None))
        tools = {"allowed_tool": ("Allowed tool", False, callback,
                                  {"type": "object", "properties": {}, "required": []})}
        for response in ({}, {"choices": []}, {"choices": [{"message": None}]},
                         self._reply(tool_calls=[self._tool_call("allowed_tool", [])])):
            with self.subTest(response=response):
                with patch.object(DeepSeekLLMApiService, "_request", return_value=response):
                    with self.assertRaises(UserError):
                        self.service.request_llm("deepseek-chat", [], ["Do it"], tools=tools)
        callback.assert_not_called()

    def test_deepseek_agent_uses_extension_service_with_history_and_tools(self):
        with patch.object(DeepSeekLLMApiService, "_request", return_value=self._reply("Addon service answer")) as request:
            answers = self.agent._generate_response(
                "Current question", chat_history=[{"role": "assistant", "content": "Prior answer"}],
            )
        self.assertEqual(answers, ["Addon service answer"])
        body = request.call_args.args[3]
        self.assertEqual(body["model"], "deepseek-chat")
        self.assertEqual(body["messages"][-2:], [
            {"role": "assistant", "content": "Prior answer"},
            {"role": "user", "content": "Current question"},
        ])

    def test_non_deepseek_agent_keeps_original_service_protocol(self):
        self.agent.llm_model = "gpt-4o"
        response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Core answer"}]}]}
        with patch.object(DeepSeekLLMApiService, "_request") as deepseek_request:
            with patch.object(LLMApiService, "_get_api_token", return_value="test-openai-token"):
                with patch.object(LLMApiService, "_request", return_value=response) as core_request:
                    answers = self.agent._generate_response("Current question")
        self.assertEqual(answers, ["Core answer"])
        self.assertEqual(core_request.call_args.args[1], "/responses")
        deepseek_request.assert_not_called()

    def test_deepseek_sources_are_rejected_on_creation_and_reassignment(self):
        Source = self.env["ai.agent.source"]
        with self.assertRaises(UserError):
            Source.create({"name": "Unsupported knowledge source", "type": "binary",
                           "status": "indexed", "agent_id": self.agent.id})
        other_agent = self.env["ai.agent"].create({"name": "Core source agent", "llm_model": "gpt-4o"})
        source = Source.create({"name": "Core knowledge source", "type": "binary",
                                "status": "indexed", "agent_id": other_agent.id})
        with self.assertRaises(UserError):
            source.write({"agent_id": self.agent.id})
        self.assertEqual(source.agent_id, other_agent)

    def test_existing_source_prevents_switching_agent_to_deepseek(self):
        other_agent = self.env["ai.agent"].create({
            "name": "Core source agent", "llm_model": "gpt-4o",
            "sources_ids": [Command.create({"name": "Existing knowledge source", "type": "binary",
                                            "status": "indexed"})],
        })
        with self.assertRaises(UserError):
            other_agent.write({"llm_model": "deepseek-chat"})
        self.assertEqual(other_agent.llm_model, "gpt-4o")

    def test_context_default_and_inline_sources_cannot_bypass_restriction(self):
        with self.assertRaises(UserError):
            self.env["ai.agent.source"].with_context(default_agent_id=self.agent.id).create({
                "name": "Source created from the agent dialog", "type": "binary", "status": "indexed",
            })
        with self.assertRaises(UserError):
            self.env["ai.agent"].create({
                "name": "DeepSeek with inline source", "llm_model": "deepseek-chat",
                "sources_ids": [Command.create({"name": "Inline source", "type": "binary", "status": "indexed"})],
            })

    def test_settings_reuses_existing_parameter_and_restricts_secret_field(self):
        field = self.env["res.config.settings"]._fields["deepseek_key"]
        self.assertEqual(field.config_parameter, "ai.deepseek_key")
        self.assertEqual(field.groups, "base.group_system")
        self.assertIn("deepseek_key_enabled", self.env["res.config.settings"]._fields)

    def test_uninstall_preserves_agents_topics_and_customer_token(self):
        topic = self.env["ai.topic"].create({"name": "Keep this business topic"})
        self.agent.topic_ids = [Command.link(topic.id)]
        other_agent = self.env["ai.agent"].create({"name": "Reasoner agent", "llm_model": "deepseek-reasoner"})
        uninstall_hook(self.env)
        self.assertTrue(self.agent.exists())
        self.assertTrue(other_agent.exists())
        self.assertEqual(self.agent.llm_model, "gpt-4o")
        self.assertEqual(other_agent.llm_model, "gpt-4o")
        self.assertIn(topic, self.agent.topic_ids)
        self.assertEqual(self.parameters.get_param("ai.deepseek_key"), "test-deepseek-token")
