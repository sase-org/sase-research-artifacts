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
from sase.llm_provider.provider_disable import disable_provider
from sase.xprompt.loader_sources import load_xprompts_from_plugins
from sase.xprompt.models import UNSET
from sase.xprompt.processor import expand_single_xprompt
from sase.xprompt.runtime_context import bind_runtime_template_vars
from sase.xprompt.workflow_executor_utils import render_template

# Authored capacity=0 is preserved in the swarm expansion (not treated as
# omission) and rejected by current SASE at parse time.
_ZERO_CAPACITY_ERROR = "at least 1"


@pytest.fixture(autouse=True)
def _isolated_sase_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keep swarm rendering independent of machine-wide provider disables."""
    home = tmp_path / "sase-home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("SASE_HOME", str(home))


def _research_xprompts() -> dict:
    xprompts = load_xprompts_from_plugins()
    return {name: xp for name, xp in xprompts.items() if name.startswith("research")}


def _swarm_body(named_args: dict[str, str]) -> str:
    xp = _research_xprompts()["research_swarm"]
    return expand_single_xprompt(
        xp, ["some topic"], named_args, preserve_segment_separators=True
    )


def _swarm_segments(
    named_args: dict[str, str],
    *,
    image: bool = False,
    linker: bool = False,
    audio: bool = False,
) -> list[str]:
    args = dict(named_args)
    if image:
        args["image"] = "true"
    if linker:
        args["linker"] = "true"
    if audio:
        args["audio"] = "true"
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
_WAIT_IMAGE_ARTIFACTS_LOOP = (
    '{% for a in wait.artifacts if a.kind == "image" %}\n'
    "- wait_name={{ a.wait_name }} label={{ a.label }} vcs_relpath={{ a.vcs_relpath }} "
    "path={{ a.path }} ref={{ a.ref }}\n"
    "{% endfor %}"
)
_WEIGHTED_QUEUE_TEMPLATE = (
    "%q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}"
    ", w=0.25{% if priority is not none %}, "
    "priority={{ priority }}{% endif %})"
)


def _without_wait_artifacts_loop(segment: str) -> str:
    return segment.replace(_WAIT_ARTIFACTS_LOOP, "").replace(
        _WAIT_IMAGE_ARTIFACTS_LOOP, ""
    )


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
    if runners is not None:
        marker = f"%q({runners}, w=0.25"
    else:
        marker = "%q(1.5x, w=0.25"
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
        if runners is None:
            assert directives.queue_capacity is None
            assert directives.queue_capacity_multiplier == 1.5
            assert directives.wait_runners is None
        else:
            assert directives.queue_capacity == runners
            assert directives.queue_capacity_multiplier is None
            assert directives.wait_runners == runners
        assert directives.wait_priority == priority

    if priority is None:
        assert all("priority=" not in segment for segment in segments)
    if runners is None:
        assert all("%q(1.5x, w=0.25" in segment for segment in segments)
    else:
        assert all(f"%q({runners}, w=0.25" in segment for segment in segments)
    assert all("capacity=" not in segment for segment in segments)


def test_all_six_research_xprompts_load() -> None:
    assert set(_research_xprompts()) == {
        "research",
        "research/audio",
        "research/image",
        "research/more",
        "research/prompt",
        "research_swarm",
    }


def test_research_audio_declares_typed_input() -> None:
    xp = _research_xprompts()["research/audio"]
    assert [(arg.name, arg.type.value) for arg in xp.inputs] == [
        ("edition", "word"),
        ("rewrite", "bool"),
    ]
    assert xp.inputs[0].default == "full"
    assert xp.inputs[1].default is False


def test_research_audio_covers_guide_lint_render_and_delivery() -> None:
    xp = _research_xprompts()["research/audio"]
    assert "sase-listen guide" in xp.content
    assert "lint --source" in xp.content
    assert "render --json" in xp.content
    assert "sase artifact create" in xp.content


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
        ("codex", "bool"),
        ("claude", "bool"),
        ("grok", "bool"),
        ("muse", "bool"),
        ("gemini", "bool"),
        ("codex_model", "word"),
        ("claude_model", "word"),
        ("grok_model", "word"),
        ("muse_model", "word"),
        ("gemini_model", "word"),
        ("lead_model", "word"),
        ("image", "bool"),
        ("image_model", "word"),
        ("linker", "bool"),
        ("linker_model", "word"),
        ("audio", "bool"),
        ("audio_model", "word"),
    ]
    assert xp.inputs[0].default is UNSET
    assert xp.inputs[1].default is None
    assert xp.inputs[2].default is None
    assert xp.inputs[3].default is None
    assert xp.inputs[4].default is True
    assert xp.inputs[5].default is True
    assert xp.inputs[6].default is False
    assert xp.inputs[7].default is False
    assert xp.inputs[8].default is False
    assert xp.inputs[9].default == "codex/gpt-6.1-sol@xhigh"
    assert xp.inputs[10].default == "claude/opus@xhigh"
    assert xp.inputs[11].default == "grok/grok-4.6@xhigh"
    assert xp.inputs[12].default == "muse/muse-spark-1.3-contributor@xhigh"
    assert xp.inputs[13].default == "agy/gemini-3.8-flash-high"
    assert xp.inputs[14].default == "@xlarge"
    assert xp.inputs[15].default is False
    assert xp.inputs[16].default == "@image"
    assert xp.inputs[17].default is False
    assert xp.inputs[18].default == "@xlarge"
    assert xp.inputs[19].default is False
    assert xp.inputs[20].default == "@audio"


def test_research_swarm_has_nine_top_level_segments() -> None:
    segments = _authored_swarm_segments()
    assert len(segments) == 9


def test_research_swarm_defaults_to_three_expanded_agents() -> None:
    segments = _swarm_segments({})
    assert len(segments) == 3
    assert all("%id(image" not in segment for segment in segments)
    assert all("%id(grk," not in segment for segment in segments)
    assert all("%id(mus," not in segment for segment in segments)
    assert all("%id(gem," not in segment for segment in segments)
    assert all("%id(linker" not in segment for segment in segments)
    cdx, cld, final = segments
    assert "sase artifact create" not in final
    assert "__final" not in final
    assert "linker" not in final
    assert "Write the consolidated report to `<name>/<name>.md`:" in final
    assert final.rstrip().endswith("└── <name>.md\n```")
    assert "%id(cdx, clan=research.{@1})" in cdx
    assert "%id(cld, clan=research.{@1})" in cld
    assert "%clan(research.{@1}" in final
    assert "some topic #research(suffix=cdx)" in cdx
    assert "some topic #research(suffix=cld)" in cld


def test_research_swarm_can_opt_into_image_agent() -> None:
    segments = _swarm_segments({}, image=True)
    assert len(segments) == 5
    *_, final, image, linker = segments
    assert "%id(image, clan=research.{@1})" in image
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "#research/image" in image
    assert "%m:@image" in image
    assert "%model:@image" not in image
    assert "%if(" not in image
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%wait:research.{@1}.final" in linker
    assert "%wait:research.{@1}.image" in linker
    assert "<name>_infographic.png" in linker
    assert "<name>__final.md" in final


def test_research_swarm_dependency_graph_preserved() -> None:
    cdx, cld, grk, mus, gem, final, image, linker, audio = _authored_swarm_segments()

    assert '%if(should_run={{ codex and ("codex" | provider_enabled("hard")) }})' in cdx
    assert "%id(cdx, clan=research.{@1})" in cdx
    assert "%m:{{ codex_model }}" in cdx
    assert "%clan(" not in cdx

    assert '%if(should_run={{ claude and ("claude" | provider_enabled("hard")) }})' in cld
    assert "%id(cld, clan=research.{@1})" in cld
    assert "%m:{{ claude_model }}" in cld
    assert "%clan(" not in cld

    assert '%if(should_run={{ grok and ("grok" | provider_enabled("hard")) }})' in grk
    assert "%id(grk, clan=research.{@1})" in grk
    assert "%m:{{ grok_model }}" in grk

    assert '%if(should_run={{ muse and ("muse" | provider_enabled("hard")) }})' in mus
    assert "%id(mus, clan=research.{@1})" in mus
    assert "%m:{{ muse_model }}" in mus
    assert "%clan(" not in mus

    assert '%if(should_run={{ gemini and ("agy" | provider_enabled("hard")) }})' in gem
    assert "%id(gem, clan=research.{@1})" in gem
    assert "%m:{{ gemini_model }}" in gem
    assert "%clan(" not in gem

    assert "%clan(research.{@1}" in final
    assert "%id:research.{@1}.final" in final
    assert "%m:{{ lead_model }}" in final
    assert "research_lead" not in final
    assert "{% for r in researchers %}%wait:research.{@1}.{{ r.short }}" in final

    assert "%id(image, clan=research.{@1})" in image
    assert "%if(should_run={{ image }})" in image
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "#research/image" in image
    assert "%m:{{ image_model }}" in image
    assert "%model:@image" not in image
    assert "%model:codex/gpt-6.1-sol" not in image

    assert "%if(should_run={{ run_linker }})" in linker
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%m:{{ linker_model }}" in linker
    assert "%wait:research.{@1}.final" in linker
    assert "{% if image %}%wait:research.{@1}.image" in linker
    assert "#fork:" not in linker
    assert "%clan(" not in linker
    assert linker.count("%q(") == 1
    assert _WEIGHTED_QUEUE_TEMPLATE in linker
    assert "priority is not none" in linker
    assert _WAIT_ARTIFACTS_LOOP in linker
    assert _WAIT_ARTIFACTS_LOOP in final
    assert _WAIT_IMAGE_ARTIFACTS_LOOP in linker
    assert _WAIT_IMAGE_ARTIFACTS_LOOP not in final
    assert _WAIT_ARTIFACTS_LOOP not in audio
    assert _WAIT_IMAGE_ARTIFACTS_LOOP not in audio

    assert "%id(audio, clan=research.{@1})" in audio
    assert "%if(should_run={{ audio }})" in audio
    assert "%wait:research.{@1}.final" in audio
    assert "{% if run_linker %}%wait:research.{@1}.linker" in audio
    assert "#fork:research.{@1}.final" in audio
    assert "#research/audio" in audio
    assert "%m:{{ audio_model }}" in audio
    assert "%model:@audio" not in audio
    assert "%clan(" not in audio
    assert audio.count("%q(") == 1
    assert _WEIGHTED_QUEUE_TEMPLATE in audio
    assert "priority is not none" in audio

    assert all(
        "priority is not none" in segment
        for segment in (cdx, cld, grk, mus, gem, final, image, linker, audio)
    )
    assert all(
        segment.count("%q(") == 1
        for segment in (cdx, cld, grk, mus, gem, final, image, linker, audio)
    )
    assert all(
        _WEIGHTED_QUEUE_TEMPLATE in segment
        for segment in (cdx, cld, grk, mus, gem, final, image, linker, audio)
    )


def test_research_swarm_lead_mentions_artifact_read_derivation() -> None:
    *_researchers, final, _image, _linker, _audio = _authored_swarm_segments()

    assert (
        "SASE derives your plan's links from the artifacts you read this turn; use\n"
        "`sase artifact read` for context you actually used."
    ) in final


def test_research_swarm_wait_argument_gates_researchers_only() -> None:
    cdx, cld, final = _swarm_segments({"wait": "research.0f.final"})

    assert "%clan(research.{@1}" in final
    assert "%id:research.{@1}.final" in final
    assert "%m:codex/gpt-6.1-sol@xhigh" in cdx
    assert "%wait:research.0f.final" in cdx
    assert "some topic #research(suffix=cdx)" in cdx

    assert "%id(cld, clan=research.{@1})" in cld
    assert "%m:claude/opus@xhigh" in cld
    assert "%wait:research.0f.final" in cld
    assert "some topic #research(suffix=cld)" in cld

    assert "%wait:research.0f.final" not in final
    assert "%m:@xlarge" in final
    assert "research_lead" not in final
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    _assert_each_segment_has_one_queue([cdx, cld, final])

    *_researchers, image, linker = _swarm_segments(
        {"wait": "research.0f.final"}, image=True
    )
    assert "%wait:research.0f.final" not in image
    assert "%wait:research.{@1}.final" in image
    assert "%m:@image" in image
    assert "%wait:research.0f.final" not in linker
    assert "%wait:research.{@1}.final" in linker


def test_research_swarm_omitted_models_use_per_provider_defaults() -> None:
    cdx, cld, final = _swarm_segments({})

    assert "%m:codex/gpt-6.1-sol@xhigh" in cdx
    assert "%m:claude/opus@xhigh" in cld
    assert "%m:@xlarge" in final
    assert "codex/gpt-6.1-sol@xhigh" not in cld + final
    assert "claude/opus@xhigh" not in cdx + final
    assert "@xlarge" not in cdx + cld
    assert "@sol_or_grok" not in cdx + cld + final
    assert "@opus_or_grok" not in cdx + cld + final


def test_research_swarm_custom_models_route_to_matching_roles_only() -> None:
    cdx, cld, grk, mus, gem, final = _swarm_segments(
        {
            "codex_model": "@codex_custom",
            "claude_model": "@claude_custom",
            "grok_model": "@grok_custom",
            "muse_model": "@muse_custom",
            "gemini_model": "@gemini_custom",
            "lead_model": "@lead_custom",
            "grok": "true",
            "muse": "true",
            "gemini": "true",
        }
    )

    assert "%m:@codex_custom" in cdx
    assert "%m:@claude_custom" in cld
    assert "%m:@grok_custom" in grk
    assert "%m:@muse_custom" in mus
    assert "%m:@gemini_custom" in gem
    assert "%m:@lead_custom" in final

    assert "@codex_custom" not in cld + grk + mus + gem + final
    assert "@claude_custom" not in cdx + grk + mus + gem + final
    assert "@grok_custom" not in cdx + cld + mus + gem + final
    assert "@muse_custom" not in cdx + cld + grk + gem + final
    assert "@gemini_custom" not in cdx + cld + grk + mus + final
    assert "@lead_custom" not in cdx + cld + grk + mus + gem
    _assert_each_segment_has_one_queue([cdx, cld, grk, mus, gem, final])


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
    assert f"%id(cdx, clan=research.{first_marker})" in first_cdx
    assert f"%id(cld, clan=research.{first_marker})" in first_cld
    assert f"%id(cdx, clan=research.{second_marker})" in second_cdx
    assert f"%id(cld, clan=research.{second_marker})" in second_cld

    cdx_segments = (first_cdx, second_cdx)
    cld_segments = (first_cld, second_cld)
    researcher_segments = cdx_segments + cld_segments
    assert all("#research(suffix=cdx)" in segment for segment in cdx_segments)
    assert all("#research(suffix=cld)" in segment for segment in cld_segments)
    assert all("report_target=" not in segment for segment in researcher_segments)

    assert f"%wait:research.{first_marker}.cdx" in _first_final
    assert f"%wait:research.{first_marker}.cld" in _first_final


def test_research_swarm_grok_and_muse_opt_in_add_segments() -> None:
    grok_segments = _swarm_segments({"grok": "true"})
    assert len(grok_segments) == 4
    cdx, cld, grk, final = grok_segments
    assert "%id(grk, clan=research.{@1})" in grk
    assert "%m:grok/grok-4.6@xhigh" in grk
    assert "some topic #research(suffix=grk)" in grk
    assert "%wait:research.{@1}.grk" in final
    _assert_each_segment_has_one_queue(grok_segments)

    muse_segments = _swarm_segments({"muse": "true"})
    assert len(muse_segments) == 4
    assert any("%id(mus, clan=research.{@1})" in s for s in muse_segments)
    mus = next(s for s in muse_segments if "%id(mus," in s)
    assert "%m:muse/muse-spark-1.3-contributor@xhigh" in mus
    assert "some topic #research(suffix=mus)" in mus
    final = muse_segments[-1]
    assert "%wait:research.{@1}.mus" in final

    both = _swarm_segments({"grok": "true", "muse": "true"})
    assert len(both) == 5
    _assert_each_segment_has_one_queue(both)


def test_research_swarm_gemini_opt_in_adds_segment() -> None:
    segments = _swarm_segments({"gemini": "true"})
    assert len(segments) == 4
    cdx, cld, gem, final = segments
    assert "%id(gem, clan=research.{@1})" in gem
    assert "%m:agy/gemini-3.8-flash-high" in gem
    assert "agy/gemini-3.8-flash-high@" not in gem
    assert "some topic #research(suffix=gem)" in gem
    assert "3-researcher swarm" in gem
    assert "%wait:research.{@1}.gem" in final
    assert "__gem.md" in final
    _assert_each_segment_has_one_queue(segments)

    all_five = _swarm_segments({"grok": "true", "muse": "true", "gemini": "true"})
    assert len(all_five) == 6
    _assert_each_segment_has_one_queue(all_five)


def test_research_swarm_hard_disabled_agy_drops_gemini_segment() -> None:
    disable_provider("agy", 900.0, source="test", mode="hard")
    segments = _swarm_segments({"gemini": "true"})
    assert len(segments) == 3
    assert all("%id(gem," not in segment for segment in segments)
    final = segments[-1]
    assert "%wait:research.{@1}.gem" not in final


def test_research_swarm_codex_false_drops_cdx() -> None:
    cld, final = _swarm_segments({"codex": "false"})
    assert "%id(cdx," not in cld + final
    assert "%id(cld, clan=research.{@1})" in cld
    assert "%wait:research.{@1}.cdx" not in final
    assert "%wait:research.{@1}.cld" in final
    assert "1-researcher swarm" in cld
    assert "only independent researcher" in cld
    _assert_each_segment_has_one_queue([cld, final])


def test_research_swarm_hard_disabled_provider_drops_segment() -> None:
    disable_provider("codex", 900.0, source="test", mode="hard")
    (cld, final) = _swarm_segments({"codex": "true"})
    assert "%id(cdx," not in cld + final
    assert "%id(cld, clan=research.{@1})" in cld
    assert "%wait:research.{@1}.cdx" not in final
    assert "%wait:research.{@1}.cld" in final
    for directives in _plan_agent_payloads([cld, final]):
        assert directives.queue_weight == 0.25


def test_research_swarm_soft_disabled_provider_keeps_segment() -> None:
    disable_provider("codex", 900.0, source="test", mode="soft")
    segments = _swarm_segments({})
    assert len(segments) == 3
    cdx, cld, final = segments
    assert "%id(cdx, clan=research.{@1})" in cdx
    assert "%id(cld, clan=research.{@1})" in cld
    assert "%wait:research.{@1}.cdx" in final
    assert "2-researcher swarm" in cdx
    _assert_each_segment_has_one_queue(segments)


def test_research_swarm_soft_disabled_agy_keeps_gemini_segment() -> None:
    disable_provider("agy", 900.0, source="test", mode="soft")
    segments = _swarm_segments({"gemini": "true"})
    assert len(segments) == 4
    assert any("%id(gem," in segment for segment in segments)


def test_research_swarm_all_researchers_off_yields_lead_only() -> None:
    (final,) = _swarm_segments(
        {
            "codex": "false",
            "claude": "false",
            "grok": "false",
            "muse": "false",
            "gemini": "false",
        }
    )
    assert "%clan(research.{@1}" in final
    assert "%id:research.{@1}.final" in final
    assert "%wait:research.{@1}.cdx" not in final
    assert "%wait:research.{@1}.cld" not in final
    assert "%wait:research.{@1}.grk" not in final
    assert "%wait:research.{@1}.mus" not in final
    assert "%wait:research.{@1}.gem" not in final
    assert "solo researcher" in final
    _assert_each_segment_has_one_queue([final])


def test_research_swarm_reports_use_provider_suffixes() -> None:
    segments = _swarm_segments({"grok": "true", "muse": "true", "gemini": "true"})
    by_id = {segment: segment for segment in segments}
    assert any("#research(suffix=cdx)" in s for s in by_id)
    assert any("#research(suffix=cld)" in s for s in by_id)
    assert any("#research(suffix=grk)" in s for s in by_id)
    assert any("#research(suffix=mus)" in s for s in by_id)
    assert any("#research(suffix=gem)" in s for s in by_id)
    assert all("#research(suffix=a)" not in s for s in segments)
    assert all("#research(suffix=b)" not in s for s in segments)
    final = segments[-1]
    assert "cdx" in final and "cld" in final
    assert "__cdx.md" in final and "__cld.md" in final


def test_research_swarm_clan_resolves_from_lead_declaration() -> None:
    """The clan declaration lives on the lead, the only unconditional agent."""
    segments = _swarm_segments({})
    payloads = _plan_agent_payloads(segments)
    assert len(payloads) == 3
    clans = {payload.clan for payload in payloads}
    assert len(clans) == 1
    clan = next(iter(clans))
    assert clan is not None and clan.startswith("research.")
    declarers = [payload for payload in payloads if payload.clan_declared]
    assert len(declarers) == 1
    (lead,) = declarers
    assert lead.identity == f"{clan}.final"
    assert lead.clan_tribe == "research"
    assert lead.clan_summary is not None
    assert "RESEARCH PROMPT:" in lead.clan_summary
    assert "some topic" in lead.clan_summary


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

    *_researchers, image, linker = _swarm_segments({}, image=True)
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "%wait:research.{@1}.final" in linker
    assert "%wait:research.{@1}.image" in linker


def test_research_swarm_supplied_zero_runners_renders_on_every_agent() -> None:
    """Explicit 0 is not omission; current SASE rejects authored capacity=0."""
    cdx, cld, final = _swarm_segments({"runners": "0"})

    _assert_each_segment_has_one_queue([cdx, cld, final], runners=0)
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    *_researchers, image, linker = _swarm_segments({"runners": "0"}, image=True)
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "%wait:research.{@1}.final" in linker
    assert "%wait:research.{@1}.image" in linker


def test_research_swarm_supplied_runners_renders_on_every_agent() -> None:
    cdx, cld, final = _swarm_segments({"runners": "8"})

    _assert_each_segment_has_one_queue([cdx, cld, final], runners=8)
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    *_researchers, image, linker = _swarm_segments({"runners": "8"}, image=True)
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "%wait:research.{@1}.final" in linker
    assert "%wait:research.{@1}.image" in linker


def test_research_swarm_supplied_priority_renders_on_every_agent() -> None:
    cdx, cld, final = _swarm_segments({"priority": "5"})
    _assert_each_segment_has_one_queue([cdx, cld, final], priority=5)
    assert "%wait:" not in cdx
    assert "%wait:" not in cld
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    *_researchers, image, linker = _swarm_segments({"priority": "5"}, image=True)
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "%wait:research.{@1}.final" in linker
    assert "%wait:research.{@1}.image" in linker


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

    *_researchers, image, linker = _swarm_segments(
        {"wait": "research.0f.final", "priority": "5", "runners": "0"},
        image=True,
    )
    assert "%wait:research.0f.final" not in image
    assert "%wait:research.0f.final" not in linker
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "%m:@image" in image
    assert "%wait:research.{@1}.final" in linker
    assert "%wait:research.{@1}.image" in linker


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
    *_researchers, final, _image, _linker, _audio = _authored_swarm_segments()

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


def test_research_swarm_linker_opt_in_adds_segment() -> None:
    segments = _swarm_segments({}, linker=True)
    assert len(segments) == 4
    *_, final, linker = segments
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%m:@xlarge" in linker
    assert "%wait:research.{@1}.final" in linker
    assert "%wait:research.{@1}.image" not in linker
    assert "__final.md" in linker
    assert "sase artifact read" in linker
    assert "sase artifact create" in linker
    assert "%if(" not in linker
    assert "#fork:" not in linker
    assert "<name>_infographic.png" not in linker
    assert "Embed the infographic" not in linker

    assert "Write the consolidated report to `<name>/<name>__final.md`:" in final
    assert (
        'sase artifact create -p "<absolute-report-path>" '
        '-l "research:<repo-relative-report-path>"'
    ) in final
    assert "research:202609/<name>/<name>__final.md" in final
    assert "research.{@1}.linker" in final
    assert "Do not create `<name>/<name>.md`" in final
    assert final.rstrip().endswith("└── <name>__final.md\n```")
    _assert_each_segment_has_one_queue(segments)


def test_research_swarm_linker_model_routes_to_linker_only() -> None:
    segments = _swarm_segments(
        {"linker_model": "@linker_custom", "lead_model": "@lead_custom"},
        linker=True,
    )
    *_, final, linker = segments
    assert "%m:@linker_custom" in linker
    assert "@lead_custom" not in linker
    assert "@linker_custom" not in final
    assert "%m:@lead_custom" in final
    _assert_each_segment_has_one_queue(segments)


def test_research_swarm_image_model_routes_to_image_only() -> None:
    segments = _swarm_segments(
        {"image_model": "@image_custom", "lead_model": "@lead_custom"},
        image=True,
    )
    *_, final, image, linker = segments
    assert "%m:@image_custom" in image
    assert "@lead_custom" not in image
    assert "@image_custom" not in final
    assert "@image_custom" not in linker
    assert "%m:@lead_custom" in final
    assert "%m:@xlarge" in linker
    _assert_each_segment_has_one_queue(segments)


def test_research_swarm_image_implies_linker_without_duplicates() -> None:
    segments = _swarm_segments({}, image=True)
    assert len(segments) == 5
    *_, final, image, linker = segments
    assert "%id(image, clan=research.{@1})" in image
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%wait:research.{@1}.final" in image
    assert "%wait:research.{@1}.final" in linker
    assert "%wait:research.{@1}.image" in linker
    assert "#fork:research.{@1}.final" in image
    assert "#fork:" not in linker
    assert "Embed the infographic" in linker
    assert "<name>_infographic.png" in linker

    both = _swarm_segments({"linker": "true"}, image=True)
    assert len(both) == 5
    assert sum("%id(linker," in segment for segment in both) == 1
    _assert_each_segment_has_one_queue(segments)
    _assert_each_segment_has_one_queue(both)


def test_research_swarm_audio_false_adds_nothing() -> None:
    segments = _swarm_segments({})
    assert len(segments) == 3
    assert all("%id(audio," not in segment for segment in segments)
    assert all("#research/audio" not in segment for segment in segments)

    linker_segments = _swarm_segments({}, linker=True)
    assert len(linker_segments) == 4
    assert all("%id(audio," not in segment for segment in linker_segments)

    image_segments = _swarm_segments({}, image=True)
    assert len(image_segments) == 5
    assert all("%id(audio," not in segment for segment in image_segments)


def test_research_swarm_audio_opt_in_adds_segment_without_linker() -> None:
    segments = _swarm_segments({}, audio=True)
    assert len(segments) == 4
    *_, final, audio = segments
    assert "%id(audio, clan=research.{@1})" in audio
    assert "%m:@audio" in audio
    assert "%wait:research.{@1}.final" in audio
    assert "%wait:research.{@1}.linker" not in audio
    assert "#fork:research.{@1}.final" in audio
    assert "#research/audio" in audio
    assert "%if(" not in audio
    assert "%id(linker," not in audio
    assert "%id(linker," not in final
    assert "Write the consolidated report to `<name>/<name>.md`:" in final
    assert "<name>_narration.md" in final
    assert final.rstrip().endswith("└── <name>_narration.md\n```")
    _assert_each_segment_has_one_queue(segments)


def test_research_swarm_audio_opt_in_waits_for_linker() -> None:
    segments = _swarm_segments({}, linker=True, audio=True)
    assert len(segments) == 5
    *_, final, linker, audio = segments
    assert "%id(audio, clan=research.{@1})" in audio
    assert "%m:@audio" in audio
    assert "%wait:research.{@1}.final" in audio
    assert "%wait:research.{@1}.linker" in audio
    assert "#fork:research.{@1}.final" in audio
    assert "#research/audio" in audio
    assert "%if(" not in audio
    assert "%id(linker, clan=research.{@1})" in linker
    assert "Write the consolidated report to `<name>/<name>__final.md`:" in final
    assert "<name>_narration.md" in final
    assert final.rstrip().endswith("└── <name>_narration.md\n```")
    _assert_each_segment_has_one_queue(segments)

    image_segments = _swarm_segments({}, image=True, audio=True)
    assert len(image_segments) == 6
    *_, image_final, image, image_linker, image_audio = image_segments
    assert "%wait:research.{@1}.linker" in image_audio
    assert "#research/audio" in image_audio
    assert "%wait:research.{@1}.image" not in image_audio
    assert "<name>_narration.md" in image_final
    assert "<name>_infographic.png" in image_linker
    _assert_each_segment_has_one_queue(image_segments)


def test_research_swarm_audio_does_not_imply_linker() -> None:
    segments = _swarm_segments({}, audio=True)
    assert len(segments) == 4
    assert sum("%id(linker," in segment for segment in segments) == 0
    assert sum("%id(audio," in segment for segment in segments) == 1


def test_research_swarm_audio_model_routes_to_audio_only() -> None:
    segments = _swarm_segments(
        {"audio_model": "@audio_custom", "lead_model": "@lead_custom"},
        audio=True,
    )
    *_, final, audio = segments
    assert "%m:@audio_custom" in audio
    assert "@lead_custom" not in audio
    assert "@audio_custom" not in final
    assert "%m:@lead_custom" in final
    _assert_each_segment_has_one_queue(segments)


def test_research_swarm_audio_ignores_swarm_wait_argument() -> None:
    segments = _swarm_segments({"wait": "research.0f.final"}, audio=True)
    audio = segments[-1]
    assert "%id(audio, clan=research.{@1})" in audio
    assert "%wait:research.0f.final" not in audio
    assert "%wait:research.{@1}.final" in audio


def test_research_swarm_audio_carries_queue_options() -> None:
    segments = _swarm_segments({"runners": "8", "priority": "5"}, audio=True)
    _assert_each_segment_has_one_queue(segments, runners=8, priority=5)
    audio = segments[-1]
    assert "%id(audio, clan=research.{@1})" in audio
    assert "%q(8, w=0.25, priority=5)" in audio

    combo = _swarm_segments({"runners": "8", "priority": "5"}, image=True, audio=True)
    _assert_each_segment_has_one_queue(combo, runners=8, priority=5)


def test_research_swarm_linker_ignores_swarm_wait_argument() -> None:
    segments = _swarm_segments({"wait": "research.0f.final"}, linker=True)
    linker = segments[-1]
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%wait:research.0f.final" not in linker
    assert "%wait:research.{@1}.final" in linker


def test_research_swarm_linker_carries_queue_options() -> None:
    segments = _swarm_segments({"runners": "8", "priority": "5"}, linker=True)
    _assert_each_segment_has_one_queue(segments, runners=8, priority=5)
    linker = segments[-1]
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%q(8, w=0.25, priority=5)" in linker

    combo = _swarm_segments({"runners": "8", "priority": "5"}, image=True)
    _assert_each_segment_has_one_queue(combo, runners=8, priority=5)


def test_research_swarm_linker_final_layout_publishes_report() -> None:
    linker = _swarm_segments({}, linker=True)[-1]
    assert "Final layout:" in linker
    assert "├── <name>__cdx.md" in linker
    assert "├── <name>__cld.md" in linker
    assert "├── <name>__final.md" in linker
    assert "<name>_infographic.png" not in linker
    assert linker.rstrip().endswith("└── <name>.md\n```")

    image_linker = _swarm_segments({}, image=True)[-1]
    assert "├── <name>_infographic.png" in image_linker
    assert image_linker.rstrip().endswith("└── <name>.md\n```")

    grok_linker = _swarm_segments({"grok": "true"}, linker=True)[-1]
    assert "<name>__grk.md" in grok_linker

    solo_linker_segments = _swarm_segments(
        {
            "codex": "false",
            "claude": "false",
            "grok": "false",
            "muse": "false",
            "gemini": "false",
        },
        linker=True,
    )
    assert len(solo_linker_segments) == 2
    solo_final, solo_linker = solo_linker_segments
    assert "<name>__final.md" in solo_final
    assert (
        'sase artifact create -p "<absolute-report-path>" '
        '-l "research:<repo-relative-report-path>"'
    ) in solo_final
    assert "research.{@1}.linker" in solo_final
    assert "├── <name>__final.md" in solo_linker
    assert solo_linker.rstrip().endswith("└── <name>.md\n```")


def test_research_swarm_linker_opens_with_research_query_then_infographic() -> None:
    linker = _swarm_segments({}, linker=True)[-1]
    assert "> **Research query:** <summary>" in linker
    assert "the research query, and then the bottom-line section" in linker
    assert "## Bottom line" in linker
    assert "## Overview" in linker
    assert "infographic" not in linker

    image_linker = _swarm_segments({}, image=True)[-1]
    assert (
        "the research query, the infographic, and then the bottom-line section"
        in image_linker
    )
    assert "directly above the bottom-line section" in image_linker
    assert "right after the bottom line" not in image_linker
    research_query_pos = image_linker.index("**Research query.**")
    infographic_pos = image_linker.index("**Embed the infographic**")
    bottom_line_pos = image_linker.index("**Bottom-line section.**")
    assert research_query_pos < infographic_pos < bottom_line_pos

    for prompt in (linker, image_linker):
        assert "The only prose you write yourself" in prompt
        assert "summarize it as the file's" in prompt
        step3 = prompt.split("3. **Restructure**", 1)[1].split(
            "4. **Validate every link carried over.**", 1
        )[0]
        assert not any(
            line and not line.strip() for line in step3.splitlines()
        )


def test_research_swarm_linker_renders_registered_lead_via_wait_artifacts(
    tmp_path: Path,
) -> None:
    """Mirror the lead end-to-end render for the linker handoff."""
    artifact_files_root = tmp_path / "artifact_store"
    index_path = artifact_files_root / "artifact_files.jsonl"
    final_dir = tmp_path / "agents" / "research.m.final"
    final_dir.mkdir(parents=True)

    report = tmp_path / "topic__final.md"
    report.write_text("# Consolidated findings\n", encoding="utf-8")

    artifact = store_explicit_artifact_file(
        report,
        final_dir,
        label="research:202609/topic/topic__final.md",
        artifact_files_root=artifact_files_root,
        index_path=index_path,
    )

    artifacts = query_artifact_context(
        [ArtifactContextProducerGroup("research.m.final", [str(final_dir)])],
        index_path=index_path,
    )
    artifacts.append(
        {
            "kind": "image",
            "wait_name": "research.m.image",
            "label": "research:202609/topic/topic_infographic.png",
            "vcs_relpath": "202609/topic/topic_infographic.png",
            "path": str(tmp_path / "topic_infographic.png"),
            "ref": "file:png-id",
        }
    )

    linker = _swarm_segments({}, image=True)[-1]

    with bind_runtime_template_vars(
        {"wait": SimpleNamespace(chats=[], artifacts=artifacts)}
    ):
        rendered = render_template(linker, {})

    assert (
        "wait_name=research.m.final label=research:202609/topic/topic__final.md"
        in rendered
    )
    assert f"source_path={report}" in rendered
    assert f"path={artifact.path}" in rendered
    assert f"ref=file:{artifact.id}" in rendered
    assert "wait_name=research.m.image" in rendered
    assert "vcs_relpath=202609/topic/topic_infographic.png" in rendered
    assert "{{" not in rendered
    assert "{%" not in rendered


def test_research_image_strips_final_stem() -> None:
    xp = _research_xprompts()["research/image"]
    assert "topic__final.md" in xp.content
    assert "topic_infographic.png" in xp.content
    assert "without overwrite" in xp.content
