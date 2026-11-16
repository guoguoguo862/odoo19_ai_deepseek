from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from ..services.model_catalog import DeepSeekModelCatalog


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    deepseek_key = fields.Char(
        string="DeepSeek API Key",
        config_parameter="ai.deepseek_key",
        groups="base.group_system",
    )
    deepseek_key_enabled = fields.Boolean(
        string="Use a custom DeepSeek API key",
        compute="_compute_deepseek_key_enabled",
        readonly=False,
        groups="base.group_system",
    )
    deepseek_model_sync_status = fields.Char(
        string="Model synchronization", compute="_compute_deepseek_model_sync",
        groups="base.group_system",
    )
    deepseek_model_last_sync = fields.Datetime(
        string="Last successful synchronization", compute="_compute_deepseek_model_sync",
        groups="base.group_system",
    )
    deepseek_model_count = fields.Integer(
        string="Available text models", compute="_compute_deepseek_model_sync",
        groups="base.group_system",
    )

    @api.depends("deepseek_key")
    def _compute_deepseek_key_enabled(self):
        for settings in self:
            settings.deepseek_key_enabled = bool(settings.deepseek_key)

    @api.depends("deepseek_key")
    def _compute_deepseek_model_sync(self):
        state = DeepSeekModelCatalog(self.env).get_state()
        for settings in self:
            settings.deepseek_model_sync_status = state.get("message") or _(
                "Save a DeepSeek API key to automatically load the available models."
            )
            settings.deepseek_model_last_sync = state.get("last_success") or False
            settings.deepseek_model_count = len(state.get("models", []))

    def set_values(self):
        self.ensure_one()
        self._check_deepseek_settings_admin()
        parameters = self.env["ir.config_parameter"].sudo()
        old_key = parameters.get_param("ai.deepseek_key")
        result = super().set_values()
        new_key = parameters.get_param("ai.deepseek_key")
        catalog = DeepSeekModelCatalog(self.env)
        if old_key != new_key or not catalog.get_state().get("last_success"):
            catalog.refresh()
        self._invalidate_deepseek_sync_fields()
        return result

    def action_refresh_deepseek_models(self):
        """The button explicitly saves the entered key, including unsaved changes."""
        self.ensure_one()
        self._check_deepseek_settings_admin()
        self.env["ir.config_parameter"].sudo().set_param(
            "ai.deepseek_key", (self.deepseek_key or "").strip() or False,
        )
        result = DeepSeekModelCatalog(self.env).refresh()
        self._invalidate_deepseek_sync_fields()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("DeepSeek models"),
                "message": result["message"],
                "type": "success" if result["ok"] else "warning",
                "sticky": not result["ok"],
            },
        }

    def _check_deepseek_settings_admin(self):
        if not self.env.is_admin():
            raise AccessError(_("Only administrators can synchronize DeepSeek models."))

    def _invalidate_deepseek_sync_fields(self):
        self.invalidate_recordset([
            "deepseek_model_sync_status", "deepseek_model_last_sync", "deepseek_model_count",
        ])
