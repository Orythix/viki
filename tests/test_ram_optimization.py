"""Unit tests for 8GB RAM optimization and memory budget optimizer."""

from __future__ import annotations

from viki.core.resource_budget import RAMBudgetOptimizer


def test_ram_budget_optimizer_8gb():
    opt = RAMBudgetOptimizer(target_ram_gb=8.0)
    assert opt.max_context_tokens == 4096
    res = opt.optimize_memory()
    assert res["target_ram_gb"] == 8.0
    assert "gc_collected_objects" in res


def test_models_yaml_8gb_context_cap():
    import yaml

    with open("config/models.yaml", encoding="utf-8") as f:
        conf = yaml.safe_load(f)
    models_sec = conf.get("models", {})
    profiles = models_sec.get("profiles", {})
    assert "lmstudio-gemma4e4b-8gb" in profiles
    assert profiles["lmstudio-gemma4e4b-8gb"]["max_context_tokens"] == 4096
