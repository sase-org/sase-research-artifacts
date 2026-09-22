"""Artifact-reference and file-hook provider specs for the research sidecar.

The two module-level objects here, ``RESEARCH_REF_PROVIDER`` and
``RESEARCH_HIGHLIGHTS_HOOK``, are registered as separate ``sase_artifact_refs`` /
``sase_file_hooks`` entry points in ``pyproject.toml``. Each implements exactly one of
the two ``sase_artifact`` hookspec methods (never both on the same object): sase's
registry instantiates every discovered entry point and calls *both* hookspec methods on
it regardless of which entry-point group found it, so an object implementing both would
have its specs collected twice.

Inventory globs intentionally differ between the two providers. Both ignore generated
infographic companion Markdown pages so binary link companions do not become reports.
The ``research`` ref provider's inventory keeps ``__<suffix>`` swarm drafts, because
citing a specific researcher's draft with ``@research:...`` is legitimate. The
``research-highlights`` file hook excludes drafts, because Bryan does not want a
Highlights PDF generated per draft -- only for the consolidated report. This divergence
is intentional, not a porting bug.

The ``research`` ref provider's ``expansion_format`` uses no ``{checkout_path}``
placeholder, which makes it a *pointer* kind: ``@research:<path>`` expands to prose
naming the file and its sidecar without resolving a local clone, so a launch never
materializes the (large) research sidecar just to expand a citation. See
``plans:202608/document_ref_expansion_format.md`` in the ``sase`` repo for the pointer
vs. path-bound expansion contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sase.artifact_providers import hookimpl

_COMPANION_MARKDOWN_EXCLUDE_GLOBS = [
    "!20*/**/*_infographic.md",
    "!20*/**/*.png.md",
    "!20*/**/*.jpg.md",
    "!20*/**/*.jpeg.md",
    "!20*/**/*.gif.md",
    "!20*/**/*.webp.md",
    "!20*/**/*.svg.md",
    "!20*/**/*.pdf.md",
]
# Suffixes of the research swarm's per-researcher agents (``research.<N>.<suffix>``),
# in swarm segment order. Their drafts get no Highlights PDF.
_SWARM_RESEARCHER_SUFFIXES = ("cdx", "cld", "grk", "mus", "gem")
_RESEARCH_INVENTORY_GLOBS = [
    "20*/**/*.md",
    *_COMPANION_MARKDOWN_EXCLUDE_GLOBS,
]

RESEARCH_REF_PROVIDER_SPEC: Mapping[str, Any] = {
    "schema_version": 1,
    "provider": "research",
    "ref": {
        "kind": "research",
        "icon": "∴",
        "expansion_format": "the {repo_relative_path} file in the {sidecar_role} sidecar repo",
        "properties": {
            "create_time": {"type": "datetime", "source": "markdown_frontmatter"},
            "updated_time": {"type": "datetime", "source": "markdown_frontmatter"},
            "status": {
                "type": "enum",
                "values": ["draft", "review", "final", "archived"],
                "source": "markdown_frontmatter",
            },
            "tags": {"type": "string_list", "source": "markdown_frontmatter"},
        },
        "detail": {"fields": ["status", "create_time", "updated_time", "tags"]},
        "identity": {},
        "inventory": {"globs": _RESEARCH_INVENTORY_GLOBS},
        "publication": {"link": "vcs_permalink", "referenced_by": "markdown_table"},
        "pane": {
            "label": "Research",
            "description": "Research reports and generated companion artifacts",
            "order": 40,
            "row": {
                "title": "title",
                "badges": ["status"],
                "secondary": ["updated_time"],
                "list_fields": ["tags"],
            },
            "default_sort": [{"field": "updated_time", "direction": "desc"}],
            "facets": ["status", "tags"],
            "group_by": "status",
            "empty_state": {
                "title": "No research",
                "body": "No research documents match the current project scope and filters.",
            },
        },
    },
}

RESEARCH_HIGHLIGHTS_HOOK_SPEC: Mapping[str, Any] = {
    "schema_version": 1,
    "provider": "research-highlights",
    "required": ["command"],
    "file_hook": {
        "description": (
            "Render new research reports into Highlights PDFs for the Obsidian "
            "reading queue."
        ),
        "filters": {
            "sidecars": ["research"],
            "producers": ["commit", "sdd", "finalizer"],
            "path_globs": [
                "20*/**/*.md",
                # Researcher drafts committed at the month-dir root.
                "!20*/*__*.md",
                # Drafts and critique moved into <month>/<name>/ by the lead agent.
                "!20*/*/*__*.md",
                *_COMPANION_MARKDOWN_EXCLUDE_GLOBS,
            ],
            "agent_name_globs": [
                f"!research.*.{suffix}" for suffix in _SWARM_RESEARCHER_SUFFIXES
            ],
            "ops": ["ADD"],
        },
        "timeout": "120s",
    },
}


class _ResearchRefProvider:
    """Pluggy hookimpl exposing the ``research`` artifact-ref provider spec."""

    @hookimpl
    def artifact_ref_provider_specs(self) -> tuple[Mapping[str, Any], ...]:
        return (RESEARCH_REF_PROVIDER_SPEC,)


class _ResearchHighlightsHookProvider:
    """Pluggy hookimpl exposing the ``research-highlights`` file-hook spec."""

    @hookimpl
    def artifact_file_hook_provider_specs(self) -> tuple[Mapping[str, Any], ...]:
        return (RESEARCH_HIGHLIGHTS_HOOK_SPEC,)


RESEARCH_REF_PROVIDER = _ResearchRefProvider()
RESEARCH_HIGHLIGHTS_HOOK = _ResearchHighlightsHookProvider()
