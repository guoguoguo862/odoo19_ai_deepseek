import json
from unittest.mock import Mock, patch

from odoo import Command
from odoo.addons.ai.utils.llm_providers import PROVIDERS
from odoo.addons.ai_deepseek.hooks import uninstall_hook
from odoo.addons.ai_deepseek.models import res_config_settings as settings_module
from odoo.addons.ai_deepseek.services.deepseek_api_service import DeepSeekLLMApiService
from odoo.addons.ai_deepseek.services.model_catalog import DeepSeekModelCatalog
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDeepSeekModelCatalog(TransactionCase):
    """Model discovery must stay offline during normal ORM and chat operations."""

    def setUp(self):
        super().setUp()
        self.parameters = self.env["ir.config_parameter"].sudo()
        self.parameters.set_param("ai.deepseek_key", "test-catalog-token")
        self.parameters.set_param("ai.deepseek_models", False)
        environment = patch.dict("os.environ", {"ODOO_AI_DEEPSEEK_TOKEN": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.catalog = DeepSeekModelCatalog(self.env)
        self.service = DeepSeekLLMApiService(self.env)

    @staticmethod
    def _payload(*ids):
        return {"object": "list", "data": [
            {"id": identifier, "name": "Catalog " + identifier, "object": "model"}
            for identifier in ids
        ]}

    def _refresh(self, *ids):
        with patch.object(DeepSeekLLMApiService, "_request", return_value=self._payload(*ids)):
            result = self.catalog.refresh()
        self.assertTrue(result["ok"], result)
        return result

    def _agent(self, identifier, **values):
        return self.env["ai.agent"].create({
            "name": "Model catalog regression agent", "llm_model": identifier, **values,
        })

    def test_models_endpoint_uses_authenticated_get_and_server_labels(self):
        payload = {"data": [{"id": "future-model-v9", "name": "Future Display Name"},
                            {"id": "future-model-v10"}]}
        with patch.object(DeepSeekLLMApiService, "_request", return_value=payload) as request:
            discovered = self.service.list_models()
        args, kwargs = request.call_args
        self.assertEqual(args[:2], ("get", "/models"))
        self.assertEqual(args[2]["Authorization"], "Bearer test-catalog-token")
        self.assertIsNone(args[3])
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(discovered, [
            {"id": "future-model-v9", "name": "Future Display Name"},
            {"id": "future-model-v10", "name": "future-model-v10"},
        ])

    def test_explicit_non_text_models_are_excluded(self):
        payload = {"data": [
            {"id": "text-model", "input_modalities": ["text", "image"], "output_modalities": ["text"]},
            {"id": "unknown-capabilities"},
            {"id": "image-only", "input_modalities": ["image"]},
            {"id": "audio-output", "output_modalities": ["audio"]},
        ]}
        with patch.object(DeepSeekLLMApiService, "_request", return_value=payload):
            discovered = self.service.list_models()
        self.assertEqual({item["id"] for item in discovered}, {"text-model", "unknown-capabilities"})

    def test_invalid_or_ambiguous_api_catalog_is_rejected_as_a_whole(self):
        invalid = [None, {}, {"data": {}}, {"data": []}, {"data": [None]},
                   {"data": [{"name": "Missing ID"}]}, {"data": [{"id": ""}]},
                   self._payload("duplicate", "duplicate"), self._payload("gpt-4o")]
        for payload in invalid:
            with self.subTest(payload=payload):
                with patch.object(DeepSeekLLMApiService, "_request", return_value=payload):
                    with self.assertRaises(UserError):
                        self.service.list_models()

    def test_refresh_populates_dynamic_selection_without_global_provider_changes(self):
        result = self._refresh("future-model-v9", "future-model-v10")
        self.assertEqual(result["count"], 2)
        self.assertEqual({item["id"] for item in self.catalog.get_models()},
                         {"future-model-v9", "future-model-v10"})
        with patch.object(DeepSeekLLMApiService, "_request", side_effect=AssertionError("Unexpected network request")):
            fields = self.env["ai.agent"].fields_get(["llm_model"])
            selection = dict(fields["llm_model"]["selection"])
            self.assertIn("future-model-v9", selection)
            self.assertIn("Catalog future-model-v9", selection["future-model-v9"])
            self.assertIn("gpt-4o", selection)
            self.assertEqual(self._agent("future-model-v9")._get_provider(), "deepseek")
        self.assertNotIn("deepseek", [provider.name for provider in PROVIDERS])
        self.assertTrue(self.catalog.get_model_ids() >= {"future-model-v9", "future-model-v10"})

    def test_new_database_has_no_fabricated_legacy_model_options(self):
        # The integration database may already contain pre-migration agents.
        existing = self.env["ai.agent"].sudo().with_context(active_test=False).search([
            ("llm_model", "in", ["deepseek-chat", "deepseek-reasoner"]),
        ])
        existing.write({"llm_model": "gpt-4o"})
        with patch.object(DeepSeekLLMApiService, "_request") as request:
            self.assertEqual(self.catalog.get_selection(), [])
        request.assert_not_called()

    def test_unlisted_model_cannot_be_assigned_by_rpc(self):
        self._refresh("future-model-v9")
        with self.assertRaises(UserError):
            self._agent("invented-model")
        with self.assertRaises(UserError):
            self.env["ai.agent"].with_context(default_llm_model="invented-model").create({
                "name": "Invalid model supplied through context",
            })
        agent = self._agent("future-model-v9")
        with self.assertRaises(UserError):
            agent.write({"llm_model": "invented-model"})
        self.assertEqual(agent.llm_model, "future-model-v9")

    def test_catalog_is_persistent_and_a_new_service_reads_it_offline(self):
        self._refresh("future-model-v9")
        with patch.object(DeepSeekLLMApiService, "_request") as request:
            reloaded = DeepSeekModelCatalog(self.env)
            self.assertEqual(reloaded.get_models(), self.catalog.get_models())
            self.assertIn("future-model-v9", dict(reloaded.get_selection()))
        request.assert_not_called()

    def test_failed_refresh_keeps_last_success_and_does_not_store_api_secrets(self):
        self._refresh("future-model-v9")
        previous = json.loads(self.parameters.get_param("ai.deepseek_models"))
        with patch.object(DeepSeekLLMApiService, "list_models",
                          side_effect=UserError("Rejected test-catalog-token")):
            result = self.catalog.refresh()
        current_json = self.parameters.get_param("ai.deepseek_models")
        current = json.loads(current_json)
        self.assertFalse(result["ok"])
        self.assertEqual(current["models"], previous["models"])
        self.assertEqual(current["last_success"], previous["last_success"])
        self.assertNotIn("test-catalog-token", current_json)
        self.assertNotIn("test-catalog-token", result["message"])

    def test_invalid_refresh_cannot_replace_a_valid_catalog(self):
        self._refresh("future-model-v9")
        with patch.object(DeepSeekLLMApiService, "_request", return_value={"data": []}):
            result = self.catalog.refresh()
        self.assertFalse(result["ok"])
        self.assertEqual([item["id"] for item in self.catalog.get_models()], ["future-model-v9"])

    def test_missing_key_does_not_request_models_or_destroy_cache(self):
        self._refresh("future-model-v9")
        self.parameters.set_param("ai.deepseek_key", False)
        with patch.object(DeepSeekLLMApiService, "_request") as request:
            result = self.catalog.refresh()
        self.assertFalse(result["ok"])
        request.assert_not_called()
        self.assertEqual([item["id"] for item in self.catalog.get_models()], ["future-model-v9"])

    def test_environment_key_can_populate_catalog(self):
        self.parameters.set_param("ai.deepseek_key", False)
        with patch.dict("os.environ", {"ODOO_AI_DEEPSEEK_TOKEN": "test-env-catalog-token"}):
            with patch.object(DeepSeekLLMApiService, "_request", return_value=self._payload("env-model")) as request:
                result = self.catalog.refresh()
        self.assertTrue(result["ok"])
        self.assertEqual(request.call_args.args[2]["Authorization"], "Bearer test-env-catalog-token")

    def test_retired_models_stay_usable_for_existing_and_archived_agents(self):
        self._refresh("retired-model", "archived-model", "unused-retired-model")
        agent = self._agent("retired-model")
        archived = self._agent("archived-model", active=False)
        self._refresh("current-model")
        selection = dict(self.catalog.get_selection())
        self.assertIn("current-model", selection)
        self.assertIn("retired-model", selection)
        self.assertIn("archived-model", selection)
        self.assertNotIn("unused-retired-model", selection)
        self.assertEqual(agent.llm_model, "retired-model")
        self.assertEqual(archived.llm_model, "archived-model")
        agent.system_prompt = "Updated without switching its retired model"
        self.assertEqual(agent._get_provider(), "deepseek")
        self.assertEqual(archived._get_provider(), "deepseek")

    def test_legacy_agent_survives_upgrade_before_first_successful_sync(self):
        agent = self._agent("gpt-4o")
        # Reproduce a pre-upgrade stored value without adding a fixed menu entry.
        agent.flush_recordset(["llm_model"])
        self.env.cr.execute("UPDATE ai_agent SET llm_model=%s WHERE id=%s", ("deepseek-chat", agent.id))
        agent.invalidate_recordset(["llm_model"])
        self.assertIn("deepseek-chat", dict(self.catalog.get_selection()))
        self.assertEqual(agent._get_provider(), "deepseek")
        self._refresh("current-model")
        agent.system_prompt = "Legacy agent configuration remains editable"
        self.assertEqual(agent.llm_model, "deepseek-chat")

    def test_dynamic_model_rejects_knowledge_sources(self):
        self._refresh("future-model-v9")
        agent = self._agent("future-model-v9")
        self.assertFalse(agent._get_embedding_model())
        with self.assertRaises(UserError):
            self.env["ai.agent.source"].create({
                "name": "Unsupported catalog model source", "type": "binary",
                "status": "indexed", "agent_id": agent.id,
            })
        with self.assertRaises(UserError):
            self._agent("future-model-v9", sources_ids=[Command.create({
                "name": "Inline unsupported source", "type": "binary", "status": "indexed",
            })])

    def test_dynamic_model_is_sent_unchanged_in_non_thinking_mode(self):
        self._refresh("future-model-v9")
        agent = self._agent("future-model-v9")
        response = {"choices": [{"message": {"role": "assistant", "content": "Answer"}}]}
        with patch.object(DeepSeekLLMApiService, "_request", return_value=response) as request:
            self.assertEqual(agent._generate_response("Question"), ["Answer"])
        body = request.call_args.args[3]
        self.assertEqual(body["model"], "future-model-v9")
        self.assertEqual(body["thinking"], {"type": "disabled"})

    def test_uninstall_resets_dynamic_archived_agents_and_preserves_key(self):
        self._refresh("future-model-v9")
        agent = self._agent("future-model-v9", active=False)
        topic = self.env["ai.topic"].create({"name": "Keep dynamic model business topic"})
        agent.topic_ids = [Command.link(topic.id)]
        uninstall_hook(self.env)
        self.assertTrue(agent.exists())
        self.assertEqual(agent.llm_model, "gpt-4o")
        self.assertIn(topic, agent.topic_ids)
        self.assertEqual(self.parameters.get_param("ai.deepseek_key"), "test-catalog-token")

    def test_manual_refresh_uses_unsaved_key_and_notifies_result(self):
        settings = self.env["res.config.settings"].create({"deepseek_key": "new-test-token"})
        with patch.object(DeepSeekLLMApiService, "_request", return_value=self._payload("new-model")) as request:
            action = settings.action_refresh_deepseek_models()
        self.assertEqual(self.parameters.get_param("ai.deepseek_key"), "new-test-token")
        self.assertEqual(request.call_args.args[2]["Authorization"], "Bearer new-test-token")
        self.assertEqual(action["tag"], "display_notification")

    def test_manual_refresh_is_restricted_to_administrators(self):
        settings = self.env["res.config.settings"].create({"deepseek_key": "test-catalog-token"})
        with patch.object(DeepSeekModelCatalog, "refresh") as refresh:
            with self.assertRaises(AccessError):
                settings.with_user(self.env.ref("base.public_user")).action_refresh_deepseek_models()
        refresh.assert_not_called()

    def test_saving_changed_key_syncs_after_persisting_it(self):
        settings = self.env["res.config.settings"].create({"deepseek_key": "changed-test-token"})
        parent = Mock()
        parent.set_values.side_effect = lambda: self.parameters.set_param("ai.deepseek_key", settings.deepseek_key)
        with patch.object(settings_module, "super", create=True, return_value=parent):
            with patch.object(DeepSeekLLMApiService, "_request", return_value=self._payload("changed-key-model")) as request:
                settings_module.ResConfigSettings.set_values(settings)
        parent.set_values.assert_called_once()
        self.assertEqual(request.call_args.args[2]["Authorization"], "Bearer changed-test-token")

    def test_saving_unrelated_settings_does_not_refetch_catalog(self):
        self._refresh("future-model-v9")
        settings = self.env["res.config.settings"].create({"deepseek_key": "test-catalog-token"})
        with patch.object(settings_module, "super", create=True, return_value=Mock()):
            with patch.object(DeepSeekModelCatalog, "refresh") as refresh:
                settings_module.ResConfigSettings.set_values(settings)
        refresh.assert_not_called()

    def test_cron_refresh_updates_catalog(self):
        with patch.object(DeepSeekLLMApiService, "_request", return_value=self._payload("cron-model")):
            self.env["ai.agent"]._cron_refresh_deepseek_models()
        self.assertEqual([item["id"] for item in self.catalog.get_models()], ["cron-model"])
