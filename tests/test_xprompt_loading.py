"""Load all packaged xprompts through sase's public plugin loader and prove
the swarm's segment count and wait/fork dependency graph survive packaging.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sase.agent.multi_prompt import split_segments_protecting_fences
from sase.agent.xprompt_swarm import expand_xprompt_swarms_with_metadata
from sase.core.agent_launch_facade import plan_typed_launch_units
from sase.core.agent_launch_wire_records import AgentUnitWire
from sase.core.artifact_context_query_facade import (
    ArtifactContextProducerGroup,
    query_artifact_context,
)
from sase.core.artifact_file_explicit import store_explicit_artifact_file
from sase.xprompt.loader_sources import load_xprompts_from_plugins
from sase.xprompt.models import UNSET
from sase.xprompt.processor import expand_single_xprompt
from sase.xprompt.runtime_context import bind_runtime_template_vars
from sase.xprompt.workflow_executor_utils import render_template

# Authored capacity=0 is preserved in the swarm expansion (not treated as
# omission) and rejected by current SASE at parse time.
_ZERO_CAPACITY_ERROR = "at least 1"


def _research_xprompts() -> dict:
    xprompts = load_xprompts_from_plugins()
    return {name: xp for name, xp in xprompts.items() if name.startswith("research")}


def _swarm_body(named_args: dict[str, str]) -> str:
    xp = _research_xprompts()["research_swarm"]
    return expand_single_xprompt(
        xp, ["some topic"], named_args, preserve_segment_separators=True
    )


def _swarm_segments(
    named_args: dict[str, str], *, image: bool = False
) -> list[str]:
    args = dict(named_args)
    if image:
        args["should_generate_image"] = "true"
    return split_segments_protecting_fences(_swarm_body(args))


def _authored_swarm_segments() -> list[str]:
    xp = _research_xprompts()["research_swarm"]
    return [segment.strip() for segment in xp.content.split("\n---\n") if segment.strip()]


# The lead's runtime `wait.artifacts` loop is deliberately raw-protected so it
# survives swarm-level Jinja expansion unrendered; only actual agent-runtime
# rendering evaluates it. Strip it before asserting no stray `{%` remains from
# the swarm-level `{% if wait %}` / `%q(...)` directives.
_WAIT_ARTIFACTS_LOOP = (
    '{% for a in wait.artifacts if a.kind == "markdown" and a.label '
    'and a.label.startswith("research:") %}\n'
    "- wait_name={{ a.wait_name }} label={{ a.label }} source_path={{ a.source_path }} "
    "path={{ a.path }} ref={{ a.ref }}\n"
    "{% endfor %}"
)
_WEIGHTED_QUEUE_TEMPLATE = (
    "%q(w=0.25{% if runners is not none %}, capacity={{ runners }}{% endif %}"
    "{% if priority is not none %}, "
    "priority={{ priority }}{% endif %})"
)


def _without_wait_artifacts_loop(segment: str) -> str:
    return segment.replace(_WAIT_ARTIFACTS_LOOP, "")


def _plan_agent_payloads(segments: list[str]) -> list[AgentUnitWire]:
    plan = plan_typed_launch_units("\n---\n".join(segments), selected_project="sase")
    assert plan.diagnostics == []
    payloads = [unit.payload for unit in plan.units]
    assert len(payloads) == len(segments)
    assert all(isinstance(payload, AgentUnitWire) for payload in payloads)
    return payloads


def _assert_each_segment_has_one_queue(
    segments: list[str],
    *,
    runners: int | None = None,
    priority: int | None = None,
) -> None:
    marker = "%q(w=0.25"
    if runners is not None:
        marker += f", capacity={runners}"
    if priority is not None:
        marker += f", priority={priority}"
    marker += ")"

    for segment in segments:
        assert segment.count("%q(") == 1
        assert segment.count(marker) == 1
        assert "{%" not in _without_wait_artifacts_loop(segment)
        assert "{{ priority }}" not in segment
        assert "{{ runners }}" not in segment
        assert "runners=" not in segment

    if runners == 0:
        with pytest.raises(Exception, match=_ZERO_CAPACITY_ERROR):
            plan_typed_launch_units("\n---\n".join(segments), selected_project="sase")
        return

    for directives in _plan_agent_payloads(segments):
        assert directives.queue_weight == 0.25
        assert directives.queue_weight_explicit is True
        assert directives.queue_capacity == runners
        assert directives.wait_runners == runners
        assert directives.wait_priority == priority

    if priority is None:
        assert all("priority=" not in segment for segment in segments)
    if runners is None:
        assert all("capacity=" not in segment for segment in segments)
    else:
        assert all(f"capacity={runners}" in segment for segment in segments)


def test_all_five_research_xprompts_load() -> None:
    assert set(_research_xprompts()) == {
        "research",
        "research/image",
        "research/more",
        "research/prompt",
        "research_swarm",
    }


def test_research_prompt_declares_typed_input() -> None:
    xprompts = _research_xprompts()

    xp = xprompts["research/prompt"]
    assert [(arg.name, arg.type.value) for arg in xp.inputs] == [("prompt", "text")]

    research = xprompts["research"]
    assert [(arg.name, arg.type.value) for arg in research.inputs] == [
        ("report_target", "path"),
        ("suffix", "word"),
    ]
    assert research.inputs[0].default is None
    assert research.inputs[1].default is None


def test_research_swarm_declares_typed_input() -> None:
    xp = _research_xprompts()["research_swarm"]
    assert [(arg.name, arg.type.value) for arg in xp.inputs] == [
        ("prompt", "text"),
        ("wait", "word"),
        ("priority", "int"),
        ("runners", "int"),
        ("primary_model", "word"),
        ("second_opinion_model", "word"),
        ("lead_model", "word"),
        ("should_generate_image", "bool"),
    ]
    assert xp.inputs[0].default is UNSET
    assert xp.inputs[1].default is None
    assert xp.inputs[2].default is None
    assert xp.inputs[3].default is None
    assert xp.inputs[4].default == "@sol_or_grok"
    assert xp.inputs[5].default == "@opus_or_grok"
    assert xp.inputs[6].default == "@xlarge"
    assert xp.inputs[7].default is False


def test_research_swarm_has_four_top_level_segments() -> None:
    segments = _authored_swarm_segments()
    assert len(segments) == 4


def test_research_swarm_defaults_to_three_expanded_agents() -> None:
    segments = _swarm_segments({})
    assert len(segments) == 3
    assert all("%id(image" not in segment for segment in segments)


def test_research_swarm_can_opt_into_image_agent() -> None:
    segments = _swarm_segments({}, image=True)
    assert len(segments) == 4
    image = segments[-1]
    assert "%id(image, clan=research.{@1})" in image
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "#research/image" in image
    assert "%model:@image" in image
    assert "%if(" not in image


def test_research_swarm_dependency_graph_preserved() -> None:
    cdx, cld, final, image = _authored_swarm_segments()

    assert "%clan(research.{@1}" in cdx
    assert "%id:research.{@1}.cdx" in cdx
    assert "%m:{{ primary_model }}" in cdx

    assert "%id(cld, clan=research.{@1})" in cld
    assert "%m:{{ second_opinion_model }}" in cld

    assert "%id(final, clan=research.{@1})" in final
    assert "%m:{{ lead_model }}" in final
    assert "research_lead" not in final
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    assert "%id(image, clan=research.{@1})" in image
    assert "%if(should_run={{ should_generate_image }})" in image
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "#research/image" in image
    assert "%model:@image" in image
    assert "%model:codex/gpt-5.6-sol" not in image
    assert all(
        "priority is not none" in segment for segment in (cdx, cld, final, image)
    )
    assert all(segment.count("%q(") == 1 for segment in (cdx, cld, final, image))
    assert all(
        _WEIGHTED_QUEUE_TEMPLATE in segment for segment in (cdx, cld, final, image)
    )


def test_research_swarm_lead_mentions_artifact_read_derivation() -> None:
    _cdx, _cld, final, _image = _authored_swarm_segments()

    assert (
        "SASE derives your plan's links from the artifacts you read this turn; use\n"
        "`sase artifact read` for context you actually used."
    ) in final


def test_research_swarm_wait_argument_gates_researchers_only() -> None:
    cdx, cld, final = _swarm_segments({"wait": "research.0f.final"})

    assert "%clan(research.{@1}" in cdx
    assert "%id:research.{@1}.cdx" in cdx
    assert "%m:@sol_or_grok" in cdx
    assert "%wait:research.0f.final" in cdx
    assert "some topic #research(suffix=a)" in cdx

    assert "%id(cld, clan=research.{@1})" in cld
    assert "%m:@opus_or_grok" in cld
    assert "%wait:research.0f.final" in cld
    assert "some topic #research(suffix=b)" in cld

    assert "%wait:research.0f.final" not in final
    assert "%m:@xlarge" in final
    assert "research_lead" not in final
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    _assert_each_segment_has_one_queue([cdx, cld, final])

    *_researchers, image = _swarm_segments(
        {"wait": "research.0f.final"}, image=True
    )
    assert "%wait:research.0f.final" not in image
    assert "%wait:research.{@1}.final" in image
    assert "%model:@image" in image


def test_research_swarm_omitted_models_use_existing_role_defaults() -> None:
    cdx, cld, final = _swarm_segments({})

    assert "%m:@sol_or_grok" in cdx
    assert "%m:@opus_or_grok" in cld
    assert "%m:@xlarge" in final
    assert "@sol_or_grok" not in cld + final
    assert "@opus_or_grok" not in cdx + final
    assert "@xlarge" not in cdx + cld


def test_research_swarm_custom_models_route_to_matching_roles_only() -> None:
    cdx, cld, final = _swarm_segments(
        {
            "primary_model": "@primary_custom",
            "second_opinion_model": "@second_custom",
            "lead_model": "@lead_custom",
        }
    )

    assert "%m:@primary_custom" in cdx
    assert "%m:@second_custom" in cld
    assert "%m:@lead_custom" in final

    assert "@primary_custom" not in cld + final
    assert "@second_custom" not in cdx + final
    assert "@lead_custom" not in cdx + cld
    assert "@sol_or_grok" not in cdx + cld + final
    assert "@opus_or_grok" not in cdx + cld + final
    assert "@xlarge" not in cdx + cld
    _assert_each_segment_has_one_queue([cdx, cld, final])


def test_research_swarm_omitted_wait_leaves_researchers_ungated() -> None:
    cdx, cld, final = _swarm_segments({})

    assert "%wait:" not in cdx
    assert "%wait:" not in cld
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    assert all(
        "{%" not in _without_wait_artifacts_loop(segment)
        for segment in (cdx, cld, final)
    )
    assert all("{{ wait }}" not in segment for segment in (cdx, cld, final))
    _assert_each_segment_has_one_queue([cdx, cld, final])


def test_research_swarm_researchers_carry_distinct_suffixes() -> None:
    """Two identical dispatches keep distinct researcher suffixes."""
    with patch("sase.core.time.generate_timestamp", return_value="260820_161407"):
        first_cdx, first_cld, _first_final, second_cdx, second_cld, *_ = [
            record.prompt
            for record in expand_xprompt_swarms_with_metadata(
                [
                    "#!research_swarm: some topic",
                    "#!research_swarm: some topic",
                ]
            )
        ]

    first_marker = "{@research.swarm.260820.161407.0.1!}"
    second_marker = "{@research.swarm.260820.161407.1.1!}"
    assert f"%id:research.{first_marker}.cdx" in first_cdx
    assert f"%id(cld, clan=research.{first_marker})" in first_cld
    assert f"%id:research.{second_marker}.cdx" in second_cdx
    assert f"%id(cld, clan=research.{second_marker})" in second_cld

    cdx_segments = (first_cdx, second_cdx)
    cld_segments = (first_cld, second_cld)
    researcher_segments = cdx_segments + cld_segments
    assert all("#research(suffix=a)" in segment for segment in cdx_segments)
    assert all("#research(suffix=b)" in segment for segment in cld_segments)
    assert all("report_target=" not in segment for segment in researcher_segments)

    assert f"%wait:research.{first_marker}.cdx" in _first_final
    assert f"%wait:research.{first_marker}.cld" in _first_final


def test_research_prompt_suffix_branch_renders_without_artifacts() -> None:
    xp = _research_xprompts()["research"]

    suffix_expansion = expand_single_xprompt(xp, [], {"suffix": "a"})
    assert "__a" in suffix_expansion
    assert "<stem>__a.md" in suffix_expansion
    assert "{%" not in suffix_expansion
    assert "{{ suffix }}" not in suffix_expansion

    explicit_target_expansion = expand_single_xprompt(
        xp, [], {"report_target": "x.md", "suffix": "a"}
    )
    assert "x.md" in explicit_target_expansion
    assert "<stem>__a.md" not in explicit_target_expansion

    default_expansion = expand_single_xprompt(xp, [], {})
    assert "new markdown file under" in default_expansion
    assert "<stem>__" not in default_expansion


def test_research_swarm_omitted_priority_uses_weight_only_queue() -> None:
    cdx, cld, final = _swarm_segments({})

    _assert_each_segment_has_one_queue([cdx, cld, final])
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    *_researchers, image = _swarm_segments({}, image=True)
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image


def test_research_swarm_supplied_zero_runners_renders_on_every_agent() -> None:
    """Explicit 0 is not omission; current SASE rejects authored capacity=0."""
    cdx, cld, final = _swarm_segments({"runners": "0"})

    _assert_each_segment_has_one_queue([cdx, cld, final], runners=0)
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    *_researchers, image = _swarm_segments({"runners": "0"}, image=True)
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image


def test_research_swarm_supplied_runners_renders_on_every_agent() -> None:
    cdx, cld, final = _swarm_segments({"runners": "8"})

    _assert_each_segment_has_one_queue([cdx, cld, final], runners=8)
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    *_researchers, image = _swarm_segments({"runners": "8"}, image=True)
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image


def test_research_swarm_supplied_priority_renders_on_every_agent() -> None:
    cdx, cld, final = _swarm_segments({"priority": "5"})
    _assert_each_segment_has_one_queue([cdx, cld, final], priority=5)
    assert "%wait:" not in cdx
    assert "%wait:" not in cld
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    *_researchers, image = _swarm_segments({"priority": "5"}, image=True)
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image


def test_research_swarm_priority_zero_is_not_omission() -> None:
    cdx, cld, final = _swarm_segments({"priority": "0"})
    _assert_each_segment_has_one_queue([cdx, cld, final], priority=0)


def test_research_swarm_priority_composes_with_wait() -> None:
    cdx, cld, final = _swarm_segments(
        {"wait": "research.0f.final", "priority": "5", "runners": "0"}
    )
    _assert_each_segment_has_one_queue(
        [cdx, cld, final],
        runners=0,
        priority=5,
    )

    assert "%wait:research.0f.final" in cdx
    assert "%wait:research.0f.final" in cld
    assert "%wait:research.0f.final" not in final

    *_researchers, image = _swarm_segments(
        {"wait": "research.0f.final", "priority": "5", "runners": "0"},
        image=True,
    )
    assert "%wait:research.0f.final" not in image
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "%model:@image" in image


def test_research_registers_report_in_every_branch() -> None:
    xp = _research_xprompts()["research"]
    registration_command = (
        'sase artifact create -p "<absolute-report-path>" '
        '-l "research:<repo-relative-report-path>"'
    )

    for named_args in ({"report_target": "x.md"}, {"suffix": "a"}, {}):
        expansion = expand_single_xprompt(xp, [], named_args)
        assert registration_command in expansion


def test_research_swarm_lead_lists_wait_artifacts_not_transcripts() -> None:
    _cdx, _cld, final, _image = _authored_swarm_segments()

    assert "wait_chats" not in final
    assert (
        '{% for a in wait.artifacts if a.kind == "markdown" and a.label '
        'and a.label.startswith("research:") %}' in final
    )
    assert "wait_name={{ a.wait_name }}" in final
    assert "label={{ a.label }}" in final
    assert "source_path={{ a.source_path }}" in final
    assert "path={{ a.path }}" in final
    assert "ref={{ a.ref }}" in final
    assert "sase artifact read" in final
    assert "predecessor chat transcripts" in final


def test_research_swarm_lead_renders_registered_reports_via_wait_artifacts(
    tmp_path: Path,
) -> None:
    """Prove the real create-to-query-to-render flow end to end.

    Two reports are registered exactly as `#research` would, a third
    unrelated markdown artifact is registered under the same producer to
    prove it is filtered out, and the lead segment's actual template text
    is rendered against the real (non-mocked) artifact-context query.
    """
    artifact_files_root = tmp_path / "artifact_store"
    index_path = artifact_files_root / "artifact_files.jsonl"
    cdx_dir = tmp_path / "agents" / "research.m.cdx"
    cld_dir = tmp_path / "agents" / "research.m.cld"
    cdx_dir.mkdir(parents=True)
    cld_dir.mkdir(parents=True)

    report_a = tmp_path / "topic__a.md"
    report_a.write_text("# A findings\n", encoding="utf-8")
    report_b = tmp_path / "topic__b.md"
    report_b.write_text("# B findings\n", encoding="utf-8")
    scratch = tmp_path / "notes.md"
    scratch.write_text("scratch\n", encoding="utf-8")

    artifact_a = store_explicit_artifact_file(
        report_a,
        cdx_dir,
        label="research:202609/topic/topic__a.md",
        artifact_files_root=artifact_files_root,
        index_path=index_path,
    )
    artifact_b = store_explicit_artifact_file(
        report_b,
        cld_dir,
        label="research:202609/topic/topic__b.md",
        artifact_files_root=artifact_files_root,
        index_path=index_path,
    )
    store_explicit_artifact_file(
        scratch,
        cdx_dir,
        label="scratch notes",
        artifact_files_root=artifact_files_root,
        index_path=index_path,
    )

    artifacts = query_artifact_context(
        [
            ArtifactContextProducerGroup("research.m.cdx", [str(cdx_dir)]),
            ArtifactContextProducerGroup("research.m.cld", [str(cld_dir)]),
        ],
        index_path=index_path,
    )

    _cdx, _cld, final = _swarm_segments({})

    with bind_runtime_template_vars(
        {"wait": SimpleNamespace(chats=[], artifacts=artifacts)}
    ):
        rendered = render_template(final, {})

    assert (
        "wait_name=research.m.cdx label=research:202609/topic/topic__a.md" in rendered
    )
    assert f"source_path={report_a}" in rendered
    assert f"path={artifact_a.path}" in rendered
    assert f"ref=file:{artifact_a.id}" in rendered

    assert (
        "wait_name=research.m.cld label=research:202609/topic/topic__b.md" in rendered
    )
    assert f"source_path={report_b}" in rendered
    assert f"path={artifact_b.path}" in rendered
    assert f"ref=file:{artifact_b.id}" in rendered

    assert "scratch notes" not in rendered
    assert str(scratch) not in rendered
    assert "wait_chats" not in rendered
    assert "{{" not in rendered
    assert "{%" not in rendered
