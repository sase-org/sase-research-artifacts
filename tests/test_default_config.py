"""Verify the packaged default_config.yml loads and is schema-valid."""

from __future__ import annotations

import importlib.resources

import jsonschema

from sase.config.inventory import load_config_schema
from sase.config.loading import load_plugin_configs


def _research_default_config() -> dict:
    configs = load_plugin_configs(importlib.resources.files)
    matches = [c for c in configs if "llm_provider" in c and "ace" in c]
    assert len(matches) == 1, configs
    return matches[0]


def test_default_config_loads_expected_model_aliases_and_bucket() -> None:
    config = _research_default_config()
    custom = config["llm_provider"]["model_aliases"]["custom"]

    assert custom["research_a"]["model"] == "codex/gpt-5.6-sol"
    assert custom["research_a"]["bucket"] == "researchers"
    assert custom["research_b"]["model"] == "claude/opus"
    assert custom["research_b"]["bucket"] == "researchers"
    assert "research" "_lead" not in custom
    assert custom["image"]["model"] == "codex/gpt-5.6-sol@xhigh | grok/grok-4.6@xhigh"
    assert custom["image"]["bucket"] == "researchers"
    assert custom["image"]["description"]

    buckets = config["llm_provider"]["model_aliases"]["buckets"]
    assert "researchers" in buckets
    researchers_description = buckets["researchers"]["description"]
    assert researchers_description
    assert "infographic" in researchers_description.lower()


def test_default_config_declares_research_tribe() -> None:
    config = _research_default_config()
    tribe = config["ace"]["tribes"]["research"]

    assert tribe["icon"] == "∴"
    assert tribe["color"] == "#5FD7AF"
    assert "research_swarm" in tribe["description"]


def test_default_config_validates_against_config_schema() -> None:
    config = _research_default_config()
    schema = load_config_schema()

    jsonschema.validate(instance=config, schema=schema)
