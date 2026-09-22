"""Prove the intentional glob divergence between the ref inventory and the
file-hook filters: the ref provider's inventory keeps `__<suffix>` swarm
drafts (citing a specific researcher's draft is legitimate), while the
research-highlights file hook excludes them (no Highlights PDF per draft).
"""

from __future__ import annotations

import pytest
from sase.artifact_ref_operations import filter_artifact_ref_paths
from sase.config.file_hooks import (
    FileHookConfig,
    FileHookEvent,
    FileHookFilters,
    hook_matches_event,
)

from sase_research_artifacts.provider import (
    RESEARCH_HIGHLIGHTS_HOOK_SPEC,
    RESEARCH_REF_PROVIDER_SPEC,
)

_DEPTH_1_DRAFTS = (
    "202608/widgets__cdx.md",
    "202608/widgets__cld.md",
    "202608/widgets__grk.md",
    "202608/widgets__mus.md",
    "202608/widgets__gem.md",
)
_DEPTH_2_DRAFTS = (
    "202608/widgets/widgets__a.md",
    "202608/widgets/widgets__b.md",
)
_CANDIDATES = (
    "202608/widgets/widgets.md",
    *_DEPTH_2_DRAFTS,
    *_DEPTH_1_DRAFTS,
    "202608/solo_report.md",
    "202608/widgets/widgets_infographic.md",
    "202608/widgets/widgets.png.md",
    "notes/scratch.md",
)


def test_ref_inventory_globs_keep_swarm_drafts() -> None:
    globs = RESEARCH_REF_PROVIDER_SPEC["ref"]["inventory"]["globs"]

    result = filter_artifact_ref_paths("research", _CANDIDATES, path_globs=globs)

    assert result.allowed == (
        "202608/widgets/widgets.md",
        *_DEPTH_2_DRAFTS,
        *_DEPTH_1_DRAFTS,
        "202608/solo_report.md",
    )
    assert "202608/widgets/widgets_infographic.md" in result.filtered
    assert "202608/widgets/widgets.png.md" in result.filtered
    assert "notes/scratch.md" in result.filtered


def test_file_hook_globs_exclude_swarm_drafts() -> None:
    globs = RESEARCH_HIGHLIGHTS_HOOK_SPEC["file_hook"]["filters"]["path_globs"]

    result = filter_artifact_ref_paths(
        "research-highlights", _CANDIDATES, path_globs=globs
    )

    assert result.allowed == ("202608/widgets/widgets.md", "202608/solo_report.md")
    for draft in (*_DEPTH_2_DRAFTS, *_DEPTH_1_DRAFTS):
        assert draft in result.filtered
    assert "202608/widgets/widgets_infographic.md" in result.filtered
    assert "202608/widgets/widgets.png.md" in result.filtered
    assert "notes/scratch.md" in result.filtered


def test_file_hook_filters_restrict_to_committed_routes() -> None:
    filters = RESEARCH_HIGHLIGHTS_HOOK_SPEC["file_hook"]["filters"]

    assert filters["producers"] == ["commit", "sdd", "finalizer"]
    assert filters["sidecars"] == ["research"]
    assert filters["ops"] == ["ADD"]
    assert filters["agent_name_globs"] == [
        "!research.*.cdx",
        "!research.*.cld",
        "!research.*.grk",
        "!research.*.mus",
        "!research.*.gem",
    ]


@pytest.mark.parametrize(
    ("agent_name", "expected"),
    [
        ("research.26.cdx", False),
        ("research.26.cld", False),
        ("research.26.grk", False),
        ("research.26.mus", False),
        ("research.26.gem", False),
        ("research.26.final", True),
        ("research.26.critique", True),
        ("foo.cld", True),
        (None, True),
    ],
)
def test_file_hook_agent_veto_covers_every_swarm_researcher(
    agent_name: str | None, expected: bool
) -> None:
    filters = RESEARCH_HIGHLIGHTS_HOOK_SPEC["file_hook"]["filters"]
    hook = FileHookConfig(
        name="research-highlights",
        description=None,
        command="true",
        timeout_seconds=0,
        filters=FileHookFilters(
            agent_name_globs=tuple(filters["agent_name_globs"]),
        ),
    )
    event = FileHookEvent(
        project="sase",
        repo_kind="sidecar",
        sidecar_role="research",
        rel_path="202608/widgets/widgets.md",
        op="ADD",
        agent_name=agent_name,
    )

    assert hook_matches_event(hook, event) is expected
