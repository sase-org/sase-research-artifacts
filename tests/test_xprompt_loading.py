"""Load all packaged xprompts through sase's public plugin loader and prove
the swarm's segment count and wait/fork dependency graph survive packaging.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sase.agent.multi_prompt import split_segments_protecting_fences
from sase.agent.xprompt_swarm import expand_xprompt_swarms_with_metadata
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


def _research_xprompts() -> dict:
    xprompts = load_xprompts_from_plugins()
    return {name: xp for name, xp in xprompts.items() if name.startswith("research")}


def _swarm_segments(named_args: dict[str, str]) -> list[str]:
    xp = _research_xprompts()["research_swarm"]
    body = expand_single_xprompt(
        xp, ["some topic"], named_args, preserve_segment_separators=True
    )
    return split_segments_protecting_fences(body)


# The lead's runtime `wait.artifacts` loop is deliberately raw-protected so it
# survives swarm-level Jinja expansion unrendered; only actual agent-runtime
# rendering evaluates it. Strip it before asserting no stray `{%` remains from
# the swarm-level `{% if wait %}` / `{% if priority %}` directives.
_WAIT_ARTIFACTS_LOOP = (
    '{% for a in wait.artifacts if a.kind == "markdown" and a.label '
    'and a.label.startswith("research:") %}\n'
    "- wait_name={{ a.wait_name }} label={{ a.label }} source_path={{ a.source_path }} "
    "path={{ a.path }} ref={{ a.ref }}\n"
    "{% endfor %}"
)


def _without_wait_artifacts_loop(segment: str) -> str:
    return segment.replace(_WAIT_ARTIFACTS_LOOP, "")


def _assert_each_segment_has_one_priority(segments: list[str], value: int) -> None:
    marker = f"%wait(priority={value})"
    for segment in segments:
        assert segment.count(marker) == 1
        assert "{%" not in _without_wait_artifacts_loop(segment)
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
    assert "some topic #research(suffix=a)" in cdx

    assert "%id(cld, clan=research.{@1})" in cld
    assert "%m:@research_b" in cld
    assert "%wait:research.0f.final" in cld
    assert "some topic #research(suffix=b)" in cld

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
    assert all(
        "{%" not in _without_wait_artifacts_loop(segment)
        for segment in (cdx, cld, final, image)
    )
    assert all("{{ wait }}" not in segment for segment in (cdx, cld, final, image))
    assert all("priority=" not in segment for segment in (cdx, cld, final, image))


def test_research_swarm_researchers_carry_distinct_suffixes() -> None:
    """Two identical dispatches keep distinct researcher suffixes."""
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

    cdx_segments = (first_cdx, second_cdx)
    cld_segments = (first_cld, second_cld)
    researcher_segments = cdx_segments + cld_segments
    assert all("#research(suffix=a)" in segment for segment in cdx_segments)
    assert all("#research(suffix=b)" in segment for segment in cld_segments)
    assert all("report_target=" not in segment for segment in researcher_segments)

    assert f"%wait:research.{first_marker}.cdx" in _first_final
    assert f"%wait:research.{first_marker}.cld" in _first_final
    assert f"%wait:research.{first_marker}.final" in _first_image


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


def test_research_swarm_omitted_priority_leaves_implicit_queue() -> None:
    cdx, cld, final, image = _swarm_segments({})

    assert all("priority=" not in segment for segment in (cdx, cld, final, image))
    assert all(
        "{%" not in _without_wait_artifacts_loop(segment)
        for segment in (cdx, cld, final, image)
    )
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
    xp = _research_xprompts()["research_swarm"]
    _cdx, _cld, final, _image = split_segments_protecting_fences(xp.content)

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

    _cdx, _cld, final, _image = _swarm_segments({})

    with bind_runtime_template_vars(
        {"wait": SimpleNamespace(chats=[], artifacts=artifacts)}
    ):
        rendered = render_template(final, {})

    assert "wait_name=research.m.cdx label=research:202609/topic/topic__a.md" in rendered
    assert f"source_path={report_a}" in rendered
    assert f"path={artifact_a.path}" in rendered
    assert f"ref=file:{artifact_a.id}" in rendered

    assert "wait_name=research.m.cld label=research:202609/topic/topic__b.md" in rendered
    assert f"source_path={report_b}" in rendered
    assert f"path={artifact_b.path}" in rendered
    assert f"ref=file:{artifact_b.id}" in rendered

    assert "scratch notes" not in rendered
    assert str(scratch) not in rendered
    assert "wait_chats" not in rendered
    assert "{{" not in rendered
    assert "{%" not in rendered
