from .services.model_catalog import DeepSeekModelCatalog


def post_init_hook(env):
    DeepSeekModelCatalog(env).refresh()


def uninstall_hook(env):
    """Keep agents and credentials; return removed model choices to core's default."""
    env["ai.agent"].with_context(active_test=False).search([
        ("llm_model", "in", sorted(DeepSeekModelCatalog(env).get_model_ids())),
    ]).write({"llm_model": "gpt-4o"})
