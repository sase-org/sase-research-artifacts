"""Parse a representative research document's Markdown frontmatter into the
research ref provider's declared typed property fields.
"""

from __future__ import annotations

from datetime import datetime

from sase_macro_compat import parse_yaml_front_matter

from sase_research_artifacts.provider import RESEARCH_REF_PROVIDER_SPEC

_SAMPLE_DOCUMENT = """\
---
create_time: 2026-08-11 16:29:34
updated_time: 2026-08-11 18:02:11
status: final
tags:
  - artifact-refs
  - plugins
---

# Widgets research

Body content.
"""


def test_declared_properties_match_provider_spec() -> None:
    properties = RESEARCH_REF_PROVIDER_SPEC["ref"]["properties"]
    assert set(properties) == {"create_time", "updated_time", "status", "tags"}
    assert properties["create_time"]["type"] == "datetime"
    assert properties["updated_time"]["type"] == "datetime"
    assert properties["status"]["type"] == "enum"
    assert properties["status"]["values"] == ["draft", "review", "final", "archived"]
    assert properties["tags"]["type"] == "string_list"
    assert all(prop["source"] == "markdown_frontmatter" for prop in properties.values())


def test_sample_frontmatter_parses_into_declared_types() -> None:
    front_matter, body = parse_yaml_front_matter(_SAMPLE_DOCUMENT)

    assert front_matter is not None
    assert isinstance(front_matter["create_time"], datetime)
    assert isinstance(front_matter["updated_time"], datetime)
    assert isinstance(front_matter["status"], str)
    assert isinstance(front_matter["tags"], list)
    assert all(isinstance(tag, str) for tag in front_matter["tags"])
    assert "# Widgets research" in body


def test_detail_fields_are_all_declared_properties() -> None:
    ref = RESEARCH_REF_PROVIDER_SPEC["ref"]
    assert set(ref["detail"]["fields"]) <= set(ref["properties"])


def test_pane_declaration_references_safe_declared_fields() -> None:
    ref = RESEARCH_REF_PROVIDER_SPEC["ref"]
    pane = ref["pane"]

    assert pane["label"] == "Research"
    assert pane["row"]["title"] == "title"
    assert pane["row"]["badges"] == ["status"]
    assert pane["row"]["secondary"] == ["updated_time"]
    assert pane["row"]["list_fields"] == ["tags"]
    assert pane["default_sort"] == [{"field": "updated_time", "direction": "desc"}]
    assert pane["facets"] == ["status", "tags"]
    assert pane["group_by"] == "status"
    assert set(pane["row"]["badges"]) <= set(ref["properties"])
    assert set(pane["row"]["secondary"]) <= set(ref["properties"])
    assert set(pane["row"]["list_fields"]) <= set(ref["properties"])
