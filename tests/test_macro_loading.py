"""Load all packaged macros through sase's public plugin loader and prove
the swarm's segment count and wait/fork dependency graph survive packaging.
"""

from __future__ import annotations

from pathlib import Path
import json
import re
import shutil
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sase.agent.multi_prompt import split_segments_protecting_fences
from sase.core.agent_launch_facade import plan_typed_launch_units
from sase.core.agent_launch_wire_records import AgentUnitWire
from sase.core.artifact_context_query_facade import (
    ArtifactContextProducerGroup,
    query_artifact_context,
)
from sase.core.artifact_file_explicit import store_explicit_artifact_file
from sase.llm_provider.provider_disable import disable_provider

from sase_macro_compat import (
    UNSET,
    bind_runtime_template_vars,
    expand_macro_swarms_with_metadata,
    expand_single_macro,
    load_macros_from_plugins,
    render_toplevel_jinja2,
)

# Authored capacity=0 is preserved in the swarm expansion (not treated as
# omission) and rejected by current SASE at parse time.
_ZERO_CAPACITY_ERROR = "at least 1"


@pytest.fixture(autouse=True)
def _isolated_sase_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep swarm rendering independent of machine-wide provider disables."""
    home = tmp_path / "sase-home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("SASE_HOME", str(home))


def _research_macros() -> dict:
    macros = load_macros_from_plugins()
    return {name: xp for name, xp in macros.items() if name.startswith("research")}


def _swarm_body(named_args: dict[str, str]) -> str:
    xp = _research_macros()["research_swarm"]
    return expand_single_macro(
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
    xp = _research_macros()["research_swarm"]
    return [
        segment.strip() for segment in xp.content.split("\n---\n") if segment.strip()
    ]


# The lead's runtime `wait.artifacts` loop is deliberately raw-protected so it
# survives swarm-level Jinja expansion unrendered; only actual agent-runtime
# rendering evaluates it. Strip it before asserting no stray `{%` remains from
# the swarm-level `{% if wait %}` / `%q(...)` directives.
_WAIT_ARTIFACTS_LOOP = (
    '{% for a in wait.artifacts if a.kind == "markdown" and a.label '
    'and a.label.startswith("research:") %}\n'
    "- wait_name={{ a.wait_name }} label={{ a.label }} "
    "source_path={{ a.source_path }} path={{ a.path }} ref={{ a.ref }}\n"
    "{% endfor %}"
)
_WAIT_IMAGE_ARTIFACTS_LOOP = (
    '{% for a in wait.artifacts if a.kind == "image" %}\n'
    "- wait_name={{ a.wait_name }} label={{ a.label }} "
    "vcs_relpath={{ a.vcs_relpath }} path={{ a.path }} ref={{ a.ref }}\n"
    "{% endfor %}"
)
_WAIT_AUDIO_ARTIFACTS_LOOP = (
    '{% for a in wait.artifacts if a.kind == "file" and a.label '
    'and a.label.startswith("audio:") %}\n'
    "- wait_name={{ a.wait_name }} label={{ a.label }} "
    "path={{ a.path }} ref={{ a.ref }}\n"
    "{% endfor %}"
)
_AGENTS_AUDIO_LOOP = (
    "{% if agents is defined %}{% for key, outputs in agents.items() "
    "if outputs.audio is defined %}\n"
    "- agent={{ key }} audio={{ outputs.audio }}\n"
    "{% endfor %}{% endif %}"
)


def _render_at_launch(segment: str) -> str:
    """Render a deferred loop the way the launch-time top-level pass does.

    Uses the public launch-time renderer, which treats fenced and inline
    code as literal, unlike the workflow-step renderer. Must be called with
    the ``wait`` namespace bound via ``bind_runtime_template_vars``.
    """
    return render_toplevel_jinja2(segment)


_WEIGHTED_QUEUE_TEMPLATE = (
    "%q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}"
    ", w=0.25{% if priority is not none %}, "
    "priority={{ priority }}{% endif %})"
)


def _without_wait_artifacts_loop(segment: str) -> str:
    return (
        segment.replace(_WAIT_ARTIFACTS_LOOP, "")
        .replace(_WAIT_IMAGE_ARTIFACTS_LOOP, "")
        .replace(_WAIT_AUDIO_ARTIFACTS_LOOP, "")
        .replace(_AGENTS_AUDIO_LOOP, "")
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


def test_all_six_research_macros_load() -> None:
    assert set(_research_macros()) == {
        "research",
        "research/audio",
        "research/image",
        "research/more",
        "research/prompt",
        "research_swarm",
    }


def test_input_types_yml_is_importable_from_the_package() -> None:
    import importlib.resources

    text = (
        importlib.resources.files("sase_research_artifacts")
        .joinpath("input_types.yml")
        .read_text(encoding="utf-8")
    )
    assert "audio_edition:" in text
    assert "value: brief" in text
    assert "value: full" in text


def test_research_audio_declares_typed_input() -> None:
    xp = _research_macros()["research/audio"]
    assert [(arg.name, arg.named_type or arg.type.value) for arg in xp.inputs] == [
        ("edition", "sase-research-artifacts@audio_edition"),
        ("rewrite", "bool"),
    ]
    assert xp.inputs[0].type.value == "enum"
    assert [choice.value for choice in xp.inputs[0].choices] == ["brief", "full"]
    assert xp.inputs[0].default == "brief"
    assert xp.inputs[1].default is False


def _expand_audio(named_args: dict[str, str]) -> str:
    xp = _research_macros()["research/audio"]
    return expand_single_macro(xp, [], named_args)


def test_research_audio_omitted_edition_uses_brief_guide() -> None:
    expansion = _expand_audio({})
    assert "sase-listen guide --edition brief" in expansion
    assert "edition: brief" in expansion
    assert "sase-listen guide --edition full" not in expansion


def test_research_audio_explicit_full_uses_full_guide() -> None:
    expansion = _expand_audio({"edition": "full"})
    assert "sase-listen guide --edition full" in expansion
    assert "edition: full" in expansion
    assert "sase-listen guide --edition brief" not in expansion


def test_research_audio_rejects_misspelled_edition_with_brief_suggestion() -> None:
    from sase.macro._exceptions import MacroArgumentError

    with pytest.raises(MacroArgumentError, match="did you mean `brief`"):
        _expand_audio({"edition": "breif"})


def test_research_audio_colon_shorthand_rejects_breif() -> None:
    from sase.macro._exceptions import MacroError
    from sase.macro.processor import process_macro_references_with_catalog

    catalog = {"research/audio": _research_macros()["research/audio"]}
    with pytest.raises(MacroError, match="did you mean `brief`"):
        process_macro_references_with_catalog(
            "#research/audio:breif",
            catalog,
            raise_on_error=True,
        )


def test_research_audio_covers_guide_lint_render_and_delivery() -> None:
    xp = _research_macros()["research/audio"]
    assert "sase-listen guide" in xp.content
    assert "lint --source" in xp.content
    assert "render --json" in xp.content
    assert "--generated-cover" in xp.content
    assert "sase-listen render <script> --generated-cover --json" in xp.content
    assert "sase artifact create" in xp.content
    assert '-l "audio:<episode_id>"' in xp.content
    assert "sase var set audio" in xp.content
    assert "complete normally" in xp.content
    assert "Never poll or wait for the image in this prompt" in xp.content
    assert "Do not wait for the image or linker" not in xp.content
    assert "render --help" in xp.content
    assert "audio.ok=false" in xp.content
    assert "Do not silently drop the option" in xp.content
    assert "Omit `cover`" in xp.content
    assert "as `cover` when it exists" not in xp.content


def test_research_prompt_declares_typed_input() -> None:
    macros = _research_macros()

    xp = macros["research/prompt"]
    assert [(arg.name, arg.type.value) for arg in xp.inputs] == [("prompt", "text")]

    research = macros["research"]
    assert [(arg.name, arg.type.value) for arg in research.inputs] == [
        ("report_target", "path"),
        ("suffix", "word"),
    ]
    assert research.inputs[0].default is None
    assert research.inputs[1].default is None


def test_research_swarm_declares_typed_input() -> None:
    xp = _research_macros()["research_swarm"]
    assert [(arg.name, arg.named_type or arg.type.value) for arg in xp.inputs] == [
        ("prompt", "text"),
        ("wait", "word"),
        ("priority", "int"),
        ("runners", "int"),
        ("codex", "bool"),
        ("claude", "bool"),
        ("grok", "bool"),
        ("muse", "bool"),
        ("gemini", "bool"),
        ("codex_model", "model"),
        ("claude_model", "model"),
        ("grok_model", "model"),
        ("muse_model", "model"),
        ("gemini_model", "model"),
        ("lead_model", "model"),
        ("image", "bool"),
        ("image_model", "model"),
        ("linker", "bool"),
        ("linker_model", "model"),
        ("audio", "bool"),
        ("audio_model", "model"),
        ("audio_edition", "sase-research-artifacts@audio_edition"),
    ]
    audio_edition = next(arg for arg in xp.inputs if arg.name == "audio_edition")
    assert audio_edition.type.value == "enum"
    assert [choice.value for choice in audio_edition.choices] == ["brief", "full"]
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
    assert xp.inputs[21].default == "brief"


def test_research_swarm_rejects_unroutable_model_with_suggestion() -> None:
    from sase.macro._exceptions import MacroArgumentError, MacroError
    from sase.macro.processor import process_macro_references_with_catalog

    xp = _research_macros()["research_swarm"]
    with pytest.raises(MacroArgumentError, match="did you mean"):
        expand_single_macro(xp, ["some topic"], {"claude_model": "opsu"})

    with pytest.raises(MacroError, match="did you mean"):
        process_macro_references_with_catalog(
            "#research_swarm(claude_model=opsu): some topic",
            {"research_swarm": xp},
            raise_on_error=True,
        )


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

    assert (
        '%if(should_run={{ claude and ("claude" | provider_enabled("hard")) }})' in cld
    )
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
    assert "{% if audio %}%wait:research.{@1}.audio" in linker
    assert "#fork:" not in linker
    assert "%clan(" not in linker
    assert linker.count("%q(") == 1
    assert _WEIGHTED_QUEUE_TEMPLATE in linker
    assert "priority is not none" in linker
    assert _WAIT_ARTIFACTS_LOOP in linker
    assert _WAIT_ARTIFACTS_LOOP in final
    assert _WAIT_IMAGE_ARTIFACTS_LOOP in linker
    assert _WAIT_IMAGE_ARTIFACTS_LOOP not in final
    assert _WAIT_AUDIO_ARTIFACTS_LOOP in linker
    assert _AGENTS_AUDIO_LOOP in linker
    assert _WAIT_AUDIO_ARTIFACTS_LOOP not in final
    assert _AGENTS_AUDIO_LOOP not in final
    assert _WAIT_ARTIFACTS_LOOP not in audio
    assert _WAIT_IMAGE_ARTIFACTS_LOOP not in audio
    assert _WAIT_AUDIO_ARTIFACTS_LOOP not in audio
    assert _AGENTS_AUDIO_LOOP not in audio

    assert "%id(audio, clan=research.{@1})" in audio
    assert "%if(should_run={{ audio }})" in audio
    assert "%wait:research.{@1}.final" in audio
    assert "%wait:research.{@1}.image" not in audio
    assert "{% if image %}%wait:research.{@1}.image" not in audio
    assert "%wait:research.{@1}.linker" not in audio
    assert "#fork:research.{@1}.final" in audio
    assert "#research/audio(edition={{ audio_edition }})" in audio
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
            "codex_model": "codex/codex-custom",
            "claude_model": "claude/claude-custom",
            "grok_model": "grok/grok-custom",
            "muse_model": "muse/muse-custom",
            "gemini_model": "agy/gemini-custom",
            "lead_model": "codex/lead-custom",
            "grok": "true",
            "muse": "true",
            "gemini": "true",
        }
    )

    assert "%m:codex/codex-custom" in cdx
    assert "%m:claude/claude-custom" in cld
    assert "%m:grok/grok-custom" in grk
    assert "%m:muse/muse-custom" in mus
    assert "%m:agy/gemini-custom" in gem
    assert "%m:codex/lead-custom" in final

    assert "codex/codex-custom" not in cld + grk + mus + gem + final
    assert "claude/claude-custom" not in cdx + grk + mus + gem + final
    assert "grok/grok-custom" not in cdx + cld + mus + gem + final
    assert "muse/muse-custom" not in cdx + cld + grk + gem + final
    assert "agy/gemini-custom" not in cdx + cld + grk + mus + final
    assert "codex/lead-custom" not in cdx + cld + grk + mus + gem
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
            for record in expand_macro_swarms_with_metadata(
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
    xp = _research_macros()["research"]

    suffix_expansion = expand_single_macro(xp, [], {"suffix": "a"})
    assert "__a" in suffix_expansion
    assert "<stem>__a.md" in suffix_expansion
    assert "{%" not in suffix_expansion
    assert "{{ suffix }}" not in suffix_expansion

    explicit_target_expansion = expand_single_macro(
        xp, [], {"report_target": "x.md", "suffix": "a"}
    )
    assert "x.md" in explicit_target_expansion
    assert "<stem>__a.md" not in explicit_target_expansion

    default_expansion = expand_single_macro(xp, [], {})
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
    xp = _research_macros()["research"]
    registration_command = (
        'sase artifact create -p "<absolute-report-path>" '
        '-l "research:<repo-relative-report-path>"'
    )

    for named_args in ({"report_target": "x.md"}, {"suffix": "a"}, {}):
        expansion = expand_single_macro(xp, [], named_args)
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
        rendered = _render_at_launch(final)

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
        {"linker_model": "codex/linker-custom", "lead_model": "codex/lead-custom"},
        linker=True,
    )
    *_, final, linker = segments
    assert "%m:codex/linker-custom" in linker
    assert "codex/lead-custom" not in linker
    assert "codex/linker-custom" not in final
    assert "%m:codex/lead-custom" in final
    _assert_each_segment_has_one_queue(segments)


def test_research_swarm_image_model_routes_to_image_only() -> None:
    segments = _swarm_segments(
        {"image_model": "agy/image-custom", "lead_model": "codex/lead-custom"},
        image=True,
    )
    *_, final, image, linker = segments
    assert "%m:agy/image-custom" in image
    assert "codex/lead-custom" not in image
    assert "agy/image-custom" not in final
    assert "agy/image-custom" not in linker
    assert "%m:codex/lead-custom" in final
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


def test_research_swarm_audio_opt_in_adds_segment_with_linker() -> None:
    segments = _swarm_segments({}, audio=True)
    assert len(segments) == 5
    *_, final, linker, audio = segments
    assert "%id(audio, clan=research.{@1})" in audio
    assert "%m:@audio" in audio
    assert "%wait:research.{@1}.final" in audio
    assert "%wait:research.{@1}.linker" not in audio
    assert "#fork:research.{@1}.final" in audio
    assert "#research/audio" in audio
    assert "%if(" not in audio
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%wait:research.{@1}.audio" in linker
    assert "Write the consolidated report to `<name>/<name>__final.md`:" in final
    assert "<name>_narration.md" in final
    assert final.rstrip().endswith("└── <name>_narration.md\n```")
    _assert_each_segment_has_one_queue(segments)


def test_research_swarm_audio_opt_in_waits_only_for_lead() -> None:
    segments = _swarm_segments({}, linker=True, audio=True)
    assert len(segments) == 5
    *_, final, linker, audio = segments
    assert "%id(audio, clan=research.{@1})" in audio
    assert "%m:@audio" in audio
    assert "%wait:research.{@1}.final" in audio
    assert "%wait:research.{@1}.linker" not in audio
    assert "%wait:research.{@1}.image" not in audio
    assert "#fork:research.{@1}.final" in audio
    assert "#research/audio" in audio
    assert "%if(" not in audio
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%wait:research.{@1}.audio" in linker
    assert "Write the consolidated report to `<name>/<name>__final.md`:" in final
    assert "<name>_narration.md" in final
    assert final.rstrip().endswith("└── <name>_narration.md\n```")
    _assert_each_segment_has_one_queue(segments)

    image_segments = _swarm_segments({}, image=True, audio=True)
    assert len(image_segments) == 6
    *_, image_final, image, image_linker, image_audio = image_segments
    assert "%wait:research.{@1}.final" in image_audio
    assert "%wait:research.{@1}.linker" not in image_audio
    assert "#research/audio" in image_audio
    assert "%wait:research.{@1}.image" not in image_audio
    assert "%wait:research.{@1}.final" in image
    assert "%wait:research.{@1}.audio" in image_linker
    assert "%wait:research.{@1}.image" in image_linker
    assert "<name>_narration.md" in image_final
    assert "<name>_infographic.png" in image_linker
    _assert_each_segment_has_one_queue(image_segments)


@pytest.mark.parametrize(
    ("linker", "image"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_research_swarm_audio_planner_edges_and_lead_source(
    linker: bool, image: bool
) -> None:
    """Packaged expansion keeps audio on the lead edge across optional work."""
    from sase.macro.processor import process_macro_references_with_catalog

    segments = _swarm_segments({}, linker=linker, image=image, audio=True)
    plan = plan_typed_launch_units("\n---\n".join(segments), selected_project="sase")
    assert plan.diagnostics == []

    by_role = {
        unit.payload.identity: unit
        for unit in plan.units
        if isinstance(unit.payload, AgentUnitWire)
    }
    lead = next(
        unit
        for unit in plan.units
        if isinstance(unit.payload.identity, str)
        and unit.payload.identity.endswith(".final")
    )
    audio = by_role["audio"]
    assert [edge.logical_id for edge in audio.waits] == [lead.logical_id]
    assert all(edge.kind == "logical" for edge in audio.waits)
    assert "linker" in by_role

    if image:
        image_unit = by_role["image"]
        assert [edge.logical_id for edge in image_unit.waits] == [lead.logical_id]
        assert audio.logical_id not in [edge.logical_id for edge in image_unit.waits]
        assert image_unit.logical_id not in [edge.logical_id for edge in audio.waits]
    linker_unit = by_role["linker"]
    expected_linker_waits = [lead.logical_id]
    if image:
        expected_linker_waits.append(by_role["image"].logical_id)
    expected_linker_waits.append(audio.logical_id)
    assert [edge.logical_id for edge in linker_unit.waits] == expected_linker_waits

    expanded_audio = process_macro_references_with_catalog(
        segments[-1],
        {"research/audio": _research_macros()["research/audio"]},
        raise_on_error=True,
    )
    normalized_audio = re.sub(r"\s+", " ", expanded_audio)
    assert (
        "`<name>__final.md`, use that file even if `<name>.md` has since appeared"
        in normalized_audio
    )
    assert (
        "An explicit `@research:` input selects exactly that report" in normalized_audio
    )
    assert "use that same report for `lint --source`" in normalized_audio
    assert "Never poll or wait for the image in this prompt" in normalized_audio
    assert "Do not wait for the image or linker" not in normalized_audio
    assert "--generated-cover" in normalized_audio
    assert "sase-listen render <script> --generated-cover --json" in normalized_audio
    assert "render --help" in normalized_audio
    assert "audio.ok=false" in normalized_audio
    assert "Do not silently drop the option" in normalized_audio
    assert "as `cover` when it exists" not in normalized_audio

    lead_segment = next(
        segment for segment in segments if "%id:research.{@1}.final" in segment
    )
    assert "<name>__final.md" in lead_segment


def test_research_swarm_audio_expanded_uses_generated_cover_across_editions() -> None:
    """Full and brief expanded audio both use the generated-cover render."""

    from sase.macro.processor import process_macro_references_with_catalog

    for edition in ("brief", "full"):
        for image in (False, True):
            segments = _swarm_segments(
                {"audio_edition": edition}, image=image, audio=True
            )
            expanded = process_macro_references_with_catalog(
                segments[-1],
                {"research/audio": _research_macros()["research/audio"]},
                raise_on_error=True,
            )
            normalized = re.sub(r"\s+", " ", expanded)
            assert "sase-listen render <script> --generated-cover --json" in normalized
            assert f"sase-listen guide --edition {edition}" in normalized
            assert f"edition: {edition}" in normalized
            assert "render --help" in normalized
            assert "audio.ok=false" in normalized
            assert "as `cover` when it exists" not in normalized


def test_research_swarm_audio_implies_linker() -> None:
    segments = _swarm_segments({}, audio=True)
    assert len(segments) == 5
    assert sum("%id(linker," in segment for segment in segments) == 1
    assert sum("%id(audio," in segment for segment in segments) == 1


def test_research_swarm_audio_model_routes_to_audio_only() -> None:
    segments = _swarm_segments(
        {"audio_model": "codex/audio-custom", "lead_model": "codex/lead-custom"},
        audio=True,
    )
    *_, final, linker, audio = segments
    assert "%m:codex/audio-custom" in audio
    assert "codex/lead-custom" not in audio
    assert "codex/audio-custom" not in final
    assert "codex/audio-custom" not in linker
    assert "%m:codex/lead-custom" in final
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


def test_research_swarm_audio_edition_defaults_to_brief() -> None:
    segments = _swarm_segments({}, audio=True)
    *rest, audio = segments
    assert "#research/audio(edition=brief)" in audio
    assert "#research/audio(edition=full)" not in audio
    assert "{{ audio_edition }}" not in audio
    assert all("#research/audio" not in segment for segment in rest)


def test_research_swarm_audio_edition_propagates_explicit_values() -> None:
    for edition in ("brief", "full"):
        segments = _swarm_segments({"audio_edition": edition}, audio=True)
        *rest, audio = segments
        assert f"#research/audio(edition={edition})" in audio
        assert "{{ audio_edition }}" not in audio
        assert all("#research/audio" not in segment for segment in rest)
        _assert_each_segment_has_one_queue(segments)


def test_research_swarm_audio_edition_reaches_guide_command() -> None:
    """The swarm's nested audio call expands to the matching guide command."""
    from sase.macro.processor import process_macro_references_with_catalog

    for edition in ("brief", "full"):
        segments = _swarm_segments({"audio_edition": edition}, audio=True)
        audio = segments[-1]
        catalog = {"research/audio": _research_macros()["research/audio"]}
        expanded = process_macro_references_with_catalog(
            audio, catalog, raise_on_error=True
        )
        assert f"sase-listen guide --edition {edition}" in expanded
        assert f"edition: {edition}" in expanded


def test_research_swarm_audio_edition_alone_launches_no_audio() -> None:
    segments = _swarm_segments({"audio_edition": "full"})
    assert len(segments) == 3
    assert all("%id(audio," not in segment for segment in segments)
    assert all("%id(linker," not in segment for segment in segments)
    assert all("#research/audio" not in segment for segment in segments)
    assert all('<div class="listen">' not in segment for segment in segments)


def test_research_swarm_audio_edition_with_linker_and_image() -> None:
    linker_segments = _swarm_segments(
        {"audio_edition": "full"}, linker=True, audio=True
    )
    assert len(linker_segments) == 5
    *_, linker, audio = linker_segments
    assert "%id(linker, clan=research.{@1})" in linker
    assert "%wait:research.{@1}.audio" in linker
    assert "%wait:research.{@1}.linker" not in audio
    assert "#research/audio(edition=full)" in audio
    assert "{{ audio_edition }}" not in audio
    _assert_each_segment_has_one_queue(linker_segments)

    image_segments = _swarm_segments({"audio_edition": "full"}, image=True, audio=True)
    assert len(image_segments) == 6
    *_, image_linker, image_audio = image_segments
    assert "%wait:research.{@1}.final" in image_audio
    assert "%wait:research.{@1}.linker" not in image_audio
    assert "%wait:research.{@1}.image" not in image_audio
    assert "%wait:research.{@1}.audio" in image_linker
    assert "#research/audio(edition=full)" in image_audio
    assert "{{ audio_edition }}" not in image_audio
    _assert_each_segment_has_one_queue(image_segments)


def test_research_swarm_linker_listen_card_only_when_audio() -> None:
    audio_linker = _swarm_segments({}, audio=True)[-2]
    assert "%id(linker, clan=research.{@1})" in audio_linker
    assert "**Listen card.**" in audio_linker
    assert '<div class="listen">' in audio_linker
    assert "♫ **Brief audio edition**" in audio_linker
    assert _AGENTS_AUDIO_LOOP in audio_linker
    assert _WAIT_AUDIO_ARTIFACTS_LOOP in audio_linker
    assert "the research query, the listen card, and then the bottom-line section" in (
        audio_linker
    )
    assert 'never write "audio pending"' in audio_linker
    assert "sase-listen ls <episode_id> --json" in audio_linker
    assert "%wait:research.{@1}.audio" in audio_linker
    _assert_each_segment_has_one_queue(_swarm_segments({}, audio=True))

    image_audio_linker = _swarm_segments({}, image=True, audio=True)[-2]
    assert (
        "the research query, the listen card, the infographic, and then "
        "the bottom-line section" in image_audio_linker
    )
    assert "**Listen card.**" in image_audio_linker
    research_query_pos = image_audio_linker.index("**Research query.**")
    listen_card_pos = image_audio_linker.index("**Listen card.**")
    infographic_pos = image_audio_linker.index("**Embed the infographic**")
    bottom_line_pos = image_audio_linker.index("**Bottom-line section.**")
    assert research_query_pos < listen_card_pos < infographic_pos < bottom_line_pos


def test_research_swarm_linker_renders_audio_handoff_at_launch() -> None:
    """The deferred agents/audio: loops render at launch from wait context."""

    class _JsonMap(dict):
        def __str__(self) -> str:
            return json.dumps(self, separators=(",", ":"), sort_keys=True)

    audio_facts = _JsonMap(
        {
            "ok": True,
            "episode_id": "ep-1",
            "edition": "brief",
            "duration_s": 250.34,
            "chapter_count": 3,
        }
    )
    linker = _swarm_segments({}, audio=True)[-2]
    with bind_runtime_template_vars(
        {
            "agents": {"research.m.audio": {"audio": audio_facts}},
            "wait": SimpleNamespace(
                chats=[],
                artifacts=[
                    {
                        "kind": "file",
                        "wait_name": "research.m.audio",
                        "label": "audio:ep-1",
                        "path": "/tmp/ep-1.mp3",
                        "ref": "file:audio-id",
                    }
                ],
            ),
        }
    ):
        rendered = _render_at_launch(linker)

    assert "agent=research.m.audio audio=" in rendered
    assert '"episode_id":"ep-1"' in rendered
    assert "wait_name=research.m.audio label=audio:ep-1" in rendered
    assert "path=/tmp/ep-1.mp3" in rendered
    assert "ref=file:audio-id" in rendered
    assert "{{" not in rendered
    assert "{%" not in rendered


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
    assert '<div class="listen">' not in linker
    assert "%wait:research.{@1}.audio" not in linker
    assert _WAIT_AUDIO_ARTIFACTS_LOOP not in linker
    assert _AGENTS_AUDIO_LOOP not in linker

    image_linker = _swarm_segments({}, image=True)[-1]
    assert (
        "the research query, the infographic, and then the bottom-line section"
        in image_linker
    )
    assert '<div class="listen">' not in image_linker
    assert "%wait:research.{@1}.audio" not in image_linker
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
        assert not any(line and not line.strip() for line in step3.splitlines())


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
        rendered = _render_at_launch(linker)

    assert (
        "wait_name=research.m.final "
        "label=research:202609/topic/topic__final.md" in rendered
    )
    assert f"source_path={report}" in rendered
    assert f"path={artifact.path}" in rendered
    assert f"ref=file:{artifact.id}" in rendered
    assert "wait_name=research.m.image" in rendered
    assert "vcs_relpath=202609/topic/topic_infographic.png" in rendered
    assert "{{" not in rendered
    assert "{%" not in rendered


def test_research_image_strips_final_stem() -> None:
    xp = _research_macros()["research/image"]
    assert "topic__final.md" in xp.content
    assert "topic_infographic.png" in xp.content
    assert "without overwrite" in xp.content


def _render_swarm_with_dunder_artifacts(tmp_path: Path) -> tuple[str, str]:
    """Render lead and linker segments against `__` labels and paths."""
    artifact_files_root = tmp_path / "artifact_store"
    index_path = artifact_files_root / "artifact_files.jsonl"
    cdx_dir = tmp_path / "agents" / "research.m.cdx"
    final_dir = tmp_path / "agents" / "research.m.final"
    cdx_dir.mkdir(parents=True)
    final_dir.mkdir(parents=True)

    report = cdx_dir / "t__cdx.md"
    report.write_text("# findings\n", encoding="utf-8")
    lead_artifact = store_explicit_artifact_file(
        report,
        cdx_dir,
        label="research:202610/t/t__cdx.md",
        artifact_files_root=artifact_files_root,
        index_path=index_path,
    )
    consolidated = final_dir / "t__final.md"
    consolidated.write_text("# consolidated\n", encoding="utf-8")
    store_explicit_artifact_file(
        consolidated,
        final_dir,
        label="research:202610/t/t__final.md",
        artifact_files_root=artifact_files_root,
        index_path=index_path,
    )

    artifacts = query_artifact_context(
        [
            ArtifactContextProducerGroup("research.m.cdx", [str(cdx_dir)]),
            ArtifactContextProducerGroup("research.m.final", [str(final_dir)]),
        ],
        index_path=index_path,
    )
    artifacts.append(
        {
            "kind": "image",
            "wait_name": "research.m.image",
            "label": "research:202610/t/t__infographic.png",
            "vcs_relpath": "202610/t/t__infographic.png",
            "path": str(tmp_path / "gh_sase-org__sase" / "t__infographic.png"),
            "ref": "file:png-id",
        }
    )

    *_, lead, _image, linker = _swarm_segments({}, image=True)
    with bind_runtime_template_vars(
        {"wait": SimpleNamespace(chats=[], artifacts=artifacts)}
    ):
        rendered_lead = _render_at_launch(lead)
        rendered_linker = _render_at_launch(linker)
    assert lead_artifact is not None
    return rendered_lead, rendered_linker


def test_research_swarm_handoff_fields_render_values_at_launch(
    tmp_path: Path,
) -> None:
    """Launch rendering substitutes every handoff field, keeping `__` intact."""
    rendered_lead, rendered_linker = _render_swarm_with_dunder_artifacts(tmp_path)

    for rendered in (rendered_lead, rendered_linker):
        loop_lines = [line for line in rendered.splitlines() if "wait_name=" in line]
        assert loop_lines, "expected rendered wait.artifacts loop lines"
        assert "{{" not in rendered
        assert "{%" not in rendered

    assert "wait_name=research.m.cdx label=research:202610/t/t__cdx.md" in rendered_lead
    assert "t__final.md" in rendered_lead
    assert "gh_sase-org__sase" in rendered_linker
    assert "202610/t/t__infographic.png" in rendered_linker


@pytest.mark.skipif(shutil.which("prettier") is None, reason="prettier is unavailable")
def test_research_swarm_handoff_fields_survive_prompt_formatting(
    tmp_path: Path,
) -> None:
    """Launch-rendered handoff labels and paths survive prompt formatting."""
    from sase.file_references import format_agent_prompt_markdown

    rendered_lead, _ = _render_swarm_with_dunder_artifacts(tmp_path)
    formatted = format_agent_prompt_markdown(rendered_lead)
    assert "research:202610/t/t__cdx.md" in formatted
    assert "research:202610/t/t__final.md" in formatted
    assert "topic**cdx" not in formatted


def test_research_macros_keep_deferred_jinja_out_of_inline_code() -> None:
    """No deferred Jinja may sit inside backticks in raw regions."""
    raw_region = re.compile(r"{% raw %}(.*?){% endraw %}", re.DOTALL)
    inline_span = re.compile(r"`[^`\n]*`")
    for name, xp in sorted(_research_macros().items()):
        for region in raw_region.findall(xp.content):
            for line in region.splitlines():
                for span in inline_span.findall(line):
                    assert "{{" not in span and "{%" not in span, (
                        f"deferred Jinja inside inline code in {name!r}: "
                        f"{span!r}; deferred loops render at launch, where "
                        "inline code is literal and {{ ... }} is never "
                        "substituted"
                    )
