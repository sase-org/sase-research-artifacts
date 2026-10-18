"""Shared wheel-install smoke for the research-artifacts plugin.

Both the source-coordination lane (`tests/test_wheel_contract.py`) and the
published-minimum lane (`.github/workflows/publish.yml`) run this script, so
it may only use APIs present at the sase floor and must stay
version-agnostic, with no version pins.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, distribution, entry_points, version
import importlib.resources

import sase.config  # avoid a circular import on a fresh interpreter
from sase.agent.multi_prompt import split_segments_protecting_fences
from sase.artifact_providers import assemble_artifact_provider_registry
from sase.config.loading import load_plugin_configs
from sase.core.agent_launch_facade import plan_typed_launch_units
from sase.macro.loader_sources import load_macros_from_plugins
from sase.macro.processor import expand_single_macro
import sase_core_rs
import sase_research_artifacts

assert (
    distribution("sase-research-artifacts").metadata["Name"]
    == "sase-research-artifacts"
)
try:
    # Guard against accidentally installing the old distribution name.
    distribution("sase-research")
except PackageNotFoundError:
    pass
else:
    raise AssertionError("old sase-research distribution is installed")
assert tuple(int(p) for p in version("sase-core-rs").split(".")[:2]) >= (0, 35)
assert hasattr(sase_core_rs, "runner_capacity_snapshot")
assert hasattr(sase_core_rs, "runner_capacity_policy_schema_version")
assert sase_core_rs.runner_capacity_policy_schema_version() >= 4
assert sase_research_artifacts.RESEARCH_REF_PROVIDER

expected = {
    "sase_artifact_refs": {
        "research": "sase_research_artifacts.provider:RESEARCH_REF_PROVIDER"
    },
    "sase_file_hooks": {
        "research-highlights": "sase_research_artifacts.provider:RESEARCH_HIGHLIGHTS_HOOK"
    },
    "sase_config": {"sase_research_artifacts": "sase_research_artifacts"},
    "sase_macros": {"sase_research_artifacts": "sase_research_artifacts"},
    "sase_xprompts": {"sase_research_artifacts": "sase_research_artifacts"},
}
discovered = entry_points()
for group, entries in expected.items():
    actual = {ep.name: ep.value for ep in discovered.select(group=group)}
    for name, value in entries.items():
        assert actual.get(name) == value, (group, name, actual.get(name))

registry = assemble_artifact_provider_registry()
assert registry.diagnostics == (), registry.diagnostics
assert "research" in registry.ref_providers_by_id
assert "research-highlights" in registry.file_hook_providers_by_id

macros = load_macros_from_plugins()
research_names = {n for n in macros if n.startswith("research")}
assert research_names == {
    "research",
    "research/audio",
    "research/diagrams",
    "research/image",
    "research/more",
    "research/prompt",
    "research_swarm",
}, research_names
research_swarm = macros["research_swarm"]
assert set(research_swarm.local_macros) == {"_queue", "_report_records"}
assert "default: 16" not in research_swarm.content


def agent_payloads_for_segments(segments):
    plan = plan_typed_launch_units("\n---\n".join(segments), selected_project="sase")
    assert plan.diagnostics == []
    payloads = [unit.payload for unit in plan.units]
    assert len(payloads) == len(segments)
    assert all(type(payload).__name__ == "AgentUnitWire" for payload in payloads)
    return payloads


def assert_segments(named_args, *, runners=None, priority=None, image=False):
    args = dict(named_args)
    if image:
        args["image"] = "true"
    body = expand_single_macro(
        research_swarm,
        ["wheel contract smoke"],
        args,
        preserve_segment_separators=True,
    )
    segments = split_segments_protecting_fences(body)
    assert len(segments) == (5 if image else 3), segments
    for segment in segments:
        assert segment.count("%q(") == 1
        assert "runners=" not in segment
        assert "capacity=" not in segment
        if runners is None:
            assert "%q(1.5x, w=0.25" in segment
        else:
            assert f"%q({runners}, w=0.25" in segment

    if runners == 0:
        try:
            plan_typed_launch_units("\n---\n".join(segments), selected_project="sase")
        except Exception as exc:
            assert "at least 1" in str(exc)
        else:
            raise AssertionError("expected authored capacity=0 to be rejected")
        return

    for directives in agent_payloads_for_segments(segments):
        assert directives.queue_weight == 0.25
        assert directives.queue_weight_explicit is True
        if runners is None:
            assert directives.queue_capacity is None
            assert directives.queue_capacity_multiplier == 1.5
            assert directives.wait_runners is None
        else:
            assert directives.queue_capacity == runners
            assert directives.queue_capacity_multiplier is None
            assert directives.wait_runners == runners
        assert directives.wait_priority == priority


assert_segments({})
assert_segments({}, image=True)
assert_segments({"runners": "0"}, runners=0)
assert_segments({"runners": "1"}, runners=1)
assert_segments({"priority": "0"}, priority=0)
assert_segments(
    {"wait": "upstream", "runners": "0", "priority": "5"},
    runners=0,
    priority=5,
)

configs = load_plugin_configs(importlib.resources.files)
assert any("llm_provider" in c and "ace" in c for c in configs)

print("WHEEL_CONTRACT_OK")
