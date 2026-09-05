"""Load all packaged xprompts through sase's public plugin loader and prove
the swarm's segment count and wait/fork dependency graph survive packaging.
"""

from __future__ import annotations

from unittest.mock import patch

from sase.agent.multi_prompt import split_segments_protecting_fences
from sase.agent.xprompt_swarm import expand_xprompt_swarms_with_metadata
from sase.xprompt.loader_sources import load_xprompts_from_plugins
from sase.xprompt.models import UNSET
from sase.xprompt.processor import expand_single_xprompt


def _research_xprompts() -> dict:
    xprompts = load_xprompts_from_plugins()
    return {name: xp for name, xp in xprompts.items() if name.startswith("research")}


def _swarm_segments(named_args: dict[str, str]) -> list[str]:
    xp = _research_xprompts()["research_swarm"]
    body = expand_single_xprompt(
        xp, ["some topic"], named_args, preserve_segment_separators=True
    )
    return split_segments_protecting_fences(body)


def _assert_each_segment_has_one_priority(segments: list[str], value: int) -> None:
    marker = f"%wait(priority={value})"
    for segment in segments:
        assert segment.count(marker) == 1
        assert "{%" not in segment
        assert "{{ priority }}" not in segment


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
        ("report_target", "path")
    ]
    assert research.inputs[0].default is None


def test_research_swarm_declares_typed_input() -> None:
    xp = _research_xprompts()["research_swarm"]
    assert [(arg.name, arg.type.value) for arg in xp.inputs] == [
        ("prompt", "text"),
        ("wait", "word"),
        ("priority", "int"),
    ]
    assert xp.inputs[0].default is UNSET
    assert xp.inputs[1].default is None
    assert xp.inputs[2].default is None


def test_research_swarm_has_four_top_level_segments() -> None:
    xp = _research_xprompts()["research_swarm"]
    segments = split_segments_protecting_fences(xp.content)
    assert len(segments) == 4


def test_research_swarm_dependency_graph_preserved() -> None:
    xp = _research_xprompts()["research_swarm"]
    cdx, cld, final, image = split_segments_protecting_fences(xp.content)

    assert "%clan(research.{@1}" in cdx
    assert "%id:research.{@1}.cdx" in cdx

    assert "%id(cld, clan=research.{@1})" in cld

    assert "%id(final, clan=research.{@1})" in final
    assert "%m:@xlarge" in final
    assert "research" "_lead" not in final
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final

    assert "%id(image, clan=research.{@1})" in image
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "#research/image" in image
    assert "%model:@image" in image
    assert "%model:codex/gpt-5.6-sol" not in image
    assert all("priority is not none" in segment for segment in (cdx, cld, final, image))
    assert all(
        "%wait(priority={{ priority }})" in segment
        for segment in (cdx, cld, final, image)
    )


def test_research_swarm_lead_mentions_artifact_read_derivation() -> None:
    xp = _research_xprompts()["research_swarm"]
    _cdx, _cld, final, _image = split_segments_protecting_fences(xp.content)

    assert (
        "SASE derives your plan's links from the artifacts you read this turn; use\n"
        "`sase artifact read` for context you actually used."
    ) in final


def test_research_swarm_wait_argument_gates_researchers_only() -> None:
    cdx, cld, final, image = _swarm_segments({"wait": "research.0f.final"})

    assert "%clan(research.{@1}" in cdx
    assert "%id:research.{@1}.cdx" in cdx
    assert "%model:@research_a" in cdx
    assert "%wait:research.0f.final" in cdx
    assert "some topic #research(report_target=research.{@1}.cdx.md)" in cdx

    assert "%id(cld, clan=research.{@1})" in cld
    assert "%m:@research_b" in cld
    assert "%wait:research.0f.final" in cld
    assert "some topic #research(report_target=research.{@1}.cld.md)" in cld

    assert "%wait:research.0f.final" not in final
    assert "%wait:research.0f.final" not in image
    assert "%m:@xlarge" in final
    assert "research" "_lead" not in final
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    assert "%wait:research.{@1}.final" in image
    assert "%model:@image" in image
    assert all("priority=" not in segment for segment in (cdx, cld, final, image))


def test_research_swarm_omitted_wait_leaves_researchers_ungated() -> None:
    cdx, cld, final, image = _swarm_segments({})

    assert "%wait:" not in cdx
    assert "%wait:" not in cld
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    assert "%wait:research.{@1}.final" in image
    assert "%model:@image" in image
    assert all("{%" not in segment for segment in (cdx, cld, final, image))
    assert all("{{ wait }}" not in segment for segment in (cdx, cld, final, image))
    assert all("priority=" not in segment for segment in (cdx, cld, final, image))


def test_research_swarm_dispatches_distinct_deterministic_report_targets() -> None:
    """Two identical dispatches under one clock get distinct report targets."""
    with patch("sase.core.time.generate_timestamp", return_value="260820_161407"):
        first_cdx, first_cld, _first_final, _first_image, second_cdx, second_cld, *_ = (
            [
                record.prompt
                for record in expand_xprompt_swarms_with_metadata(
                    [
                        "#!research_swarm: some topic",
                        "#!research_swarm: some topic",
                    ]
                )
            ]
        )

    first_marker = "{@research.swarm.260820.161407.0.1!}"
    second_marker = "{@research.swarm.260820.161407.1.1!}"
    assert f"%id:research.{first_marker}.cdx" in first_cdx
    assert f"%id(cld, clan=research.{first_marker})" in first_cld
    assert f"%id:research.{second_marker}.cdx" in second_cdx
    assert f"%id(cld, clan=research.{second_marker})" in second_cld

    targets = {
        f"research.{first_marker}.cdx.md",
        f"research.{first_marker}.cld.md",
        f"research.{second_marker}.cdx.md",
        f"research.{second_marker}.cld.md",
    }
    for target in targets:
        assert f"report_target={target}" in "\n".join(
            (first_cdx, first_cld, second_cdx, second_cld)
        )

    assert len(targets) == 4
    assert f"%wait:research.{first_marker}.cdx" in _first_final
    assert f"%wait:research.{first_marker}.cld" in _first_final
    assert f"%wait:research.{first_marker}.final" in _first_image


def test_research_swarm_omitted_priority_leaves_implicit_queue() -> None:
    cdx, cld, final, image = _swarm_segments({})

    assert all("priority=" not in segment for segment in (cdx, cld, final, image))
    assert all("{%" not in segment for segment in (cdx, cld, final, image))
    assert all("{{ priority }}" not in segment for segment in (cdx, cld, final, image))
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image


def test_research_swarm_supplied_priority_renders_on_every_agent() -> None:
    cdx, cld, final, image = _swarm_segments({"priority": "5"})
    _assert_each_segment_has_one_priority([cdx, cld, final, image], 5)
    assert "%wait:" not in cdx
    assert "%wait:" not in cld
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image


def test_research_swarm_priority_zero_is_not_omission() -> None:
    cdx, cld, final, image = _swarm_segments({"priority": "0"})
    _assert_each_segment_has_one_priority([cdx, cld, final, image], 0)


def test_research_swarm_priority_composes_with_wait() -> None:
    cdx, cld, final, image = _swarm_segments(
        {"wait": "research.0f.final", "priority": "5"}
    )
    _assert_each_segment_has_one_priority([cdx, cld, final, image], 5)

    assert "%wait:research.0f.final" in cdx
    assert "%wait:research.0f.final" in cld
    assert "%wait:research.0f.final" not in final
    assert "%wait:research.0f.final" not in image
    assert "%wait:research.{@1}.cdx" in final
    assert "%wait:research.{@1}.cld" in final
    assert "%wait:research.{@1}.final" in image
    assert "#fork:research.{@1}.final" in image
    assert "%model:@image" in image
