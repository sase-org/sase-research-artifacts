"""Contract tests for the installed research provider specs.

These exercise the real installed ``sase-research-artifacts`` distribution's entry
points through sase's own registry, sidecar-ref, and file-hook config
loaders -- not fakes standing in for our plugin. Fakes are only used to
simulate a *second*, conflicting plugin for the duplicate-diagnostic tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sase.artifact_providers import assemble_artifact_provider_registry, hookimpl
from sase.artifact_providers.registry import (
    ARTIFACT_REF_ENTRY_POINT_GROUP,
    FILE_HOOK_ENTRY_POINT_GROUP,
)
from sase.config.file_hooks import _load_file_hooks
from sase.config.layers import ConfigLayer
from sase.sidecar_ref_config import _sidecar_ref_policy_report

from sase_research_artifacts.provider import (
    RESEARCH_HIGHLIGHTS_HOOK_SPEC,
    RESEARCH_REF_PROVIDER_SPEC,
)
from tests.conftest import FakeEntryPoint, real_and_fake_entry_points


def _config_layer(hooks: object) -> ConfigLayer:
    return ConfigLayer(
        name="user",
        path=None,
        exists=True,
        list_strategy="replace",
        data={"file_hooks": hooks},
    )


def test_research_ref_provider_discovered_with_provenance() -> None:
    registry = assemble_artifact_provider_registry()

    assert registry.diagnostics == ()
    provider = registry.ref_providers_by_id["research"]
    assert provider.kind == "research"
    assert provider.provenance.group == ARTIFACT_REF_ENTRY_POINT_GROUP
    assert provider.provenance.name == "research"
    assert provider.provenance.package == "sase-research-artifacts"
    assert provider.digest


def test_research_highlights_hook_discovered_with_required_command() -> None:
    registry = assemble_artifact_provider_registry()

    provider = registry.file_hook_providers_by_id["research-highlights"]
    assert provider.required_fields == ("command",)
    assert provider.provenance.group == FILE_HOOK_ENTRY_POINT_GROUP
    assert provider.provenance.package == "sase-research-artifacts"
    assert provider.template["filters"]["sidecars"] == ["research"]
    assert provider.template["filters"]["producers"] == ["commit", "sdd", "finalizer"]


def test_duplicate_ref_kind_is_reported_and_skipped() -> None:
    class _Colliding:
        @hookimpl
        def artifact_ref_provider_specs(self) -> tuple[dict, ...]:
            return (
                {
                    "schema_version": 1,
                    "provider": "research-fork",
                    "ref": {
                        **RESEARCH_REF_PROVIDER_SPEC["ref"],
                    },
                },
            )

    fake = FakeEntryPoint(
        name="zzz-research-fork",
        group=ARTIFACT_REF_ENTRY_POINT_GROUP,
        plugin=_Colliding(),
    )
    registry = assemble_artifact_provider_registry(
        entry_points_fn=real_and_fake_entry_points(fake)
    )

    assert "research-fork" not in registry.ref_providers_by_id
    codes = {d.code for d in registry.diagnostics}
    assert "duplicate_ref_kind" in codes


def test_use_and_inline_normalize_identically(tmp_path: Path) -> None:
    provider_ref = dict(RESEARCH_REF_PROVIDER_SPEC["ref"])

    use_report = _sidecar_ref_policy_report(
        {
            "repos": {
                "sidecar": {
                    "custom": {
                        "research": {
                            "description": "Research docs.",
                            "ref": {
                                "use": "sase-research-artifacts@research",
                                "inventory": {"globs": ["2026/**/*.md"]},
                            },
                        }
                    }
                }
            }
        },
        primary_workspace_dir=tmp_path / "workspace",
        roles=("research",),
    )
    inline_report = _sidecar_ref_policy_report(
        {
            "repos": {
                "sidecar": {
                    "custom": {
                        "research": {
                            "description": "Research docs.",
                            "ref": {
                                **provider_ref,
                                "inventory": {"globs": ["2026/**/*.md"]},
                            },
                        }
                    }
                }
            }
        },
        primary_workspace_dir=tmp_path / "workspace",
        roles=("research",),
    )

    use_policy = use_report.policies["research"]
    inline_policy = inline_report.policies["research"]
    assert use_policy.spec == inline_policy.spec
    assert use_policy.digest == inline_policy.digest
    assert use_policy.path_globs == ("2026/**/*.md",)


def test_pane_only_override_preserves_provider_digest(tmp_path: Path) -> None:
    base_report = _sidecar_ref_policy_report(
        {
            "repos": {
                "sidecar": {
                    "custom": {
                        "research": {"ref": {"use": "sase-research-artifacts@research"}}
                    }
                }
            }
        },
        primary_workspace_dir=tmp_path / "workspace",
        roles=("research",),
    )
    override_report = _sidecar_ref_policy_report(
        {
            "repos": {
                "sidecar": {
                    "custom": {
                        "research": {
                            "ref": {
                                "use": "sase-research-artifacts@research",
                                "pane": {
                                    "empty_state": {
                                        "body": "No matching research reports."
                                    }
                                },
                            }
                        }
                    }
                }
            }
        },
        primary_workspace_dir=tmp_path / "workspace",
        roles=("research",),
    )

    base_policy = base_report.policies["research"]
    override_policy = override_report.policies["research"]
    assert base_policy.digest == override_policy.digest
    assert base_policy.spec != override_policy.spec
    assert (
        override_policy.spec["ref"]["pane"]["empty_state"]["body"]
        == "No matching research reports."
    )


def test_use_missing_provider_fails_soft(tmp_path: Path) -> None:
    report = _sidecar_ref_policy_report(
        {
            "repos": {
                "sidecar": {
                    "custom": {
                        "research": {
                            "description": "Research docs.",
                            "ref": {
                                "use": "sase-research-artifacts@not-a-real-provider"
                            },
                        }
                    }
                }
            }
        },
        primary_workspace_dir=tmp_path / "workspace",
        roles=("research",),
    )

    assert "research" not in report.policies
    assert report.diagnostics[0].code == "missing_ref_provider"


def test_research_highlights_use_resolves_with_local_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layers = [
        _config_layer(
            [
                {
                    "use": "sase-research-artifacts@research-highlights",
                    "command": "bob highlights create --include-id",
                }
            ]
        )
    ]
    monkeypatch.setattr(
        "sase.config.file_hooks.current_config_token", lambda: ("token-a",)
    )
    monkeypatch.setattr("sase.config.file_hooks.load_config_layers", lambda: layers)

    hooks = _load_file_hooks()

    assert len(hooks) == 1
    hook = hooks[0]
    assert hook.name == "research-highlights"
    assert hook.command == "bob highlights create --include-id"
    assert hook.timeout_seconds == 120
    assert hook.filters.sidecars == ("research",)
    assert hook.filters.producers == ("commit", "sdd", "finalizer")
    assert hook.filters.path_globs == (
        "20*/**/*.md",
        "!20*/*__*.md",
        "!20*/*/*__*.md",
        "!20*/**/*_infographic.md",
        "!20*/**/*.png.md",
        "!20*/**/*.jpg.md",
        "!20*/**/*.jpeg.md",
        "!20*/**/*.gif.md",
        "!20*/**/*.webp.md",
        "!20*/**/*.svg.md",
        "!20*/**/*.pdf.md",
    )
    assert hook.filters.agent_name_globs == (
        "!research.*.cdx",
        "!research.*.cld",
        "!research.*.grk",
        "!research.*.mus",
        "!research.*.gem",
    )
    assert hook.filters.ops == ("ADD",)


def test_research_highlights_use_without_command_fails_soft(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    layers = [_config_layer([{"use": "sase-research-artifacts@research-highlights"}])]
    monkeypatch.setattr(
        "sase.config.file_hooks.current_config_token", lambda: ("token-b",)
    )
    monkeypatch.setattr("sase.config.file_hooks.load_config_layers", lambda: layers)

    with caplog.at_level(logging.WARNING):
        hooks = _load_file_hooks()

    assert hooks == []
    assert "requires local field 'command'" in caplog.text


def test_research_highlights_local_filters_replace_not_concatenate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layers = [
        _config_layer(
            [
                {
                    "use": "sase-research-artifacts@research-highlights",
                    "command": "bob highlights create --include-id",
                    "filters": {"path_globs": ["final/**/*.md"]},
                }
            ]
        )
    ]
    monkeypatch.setattr(
        "sase.config.file_hooks.current_config_token", lambda: ("token-c",)
    )
    monkeypatch.setattr("sase.config.file_hooks.load_config_layers", lambda: layers)

    hooks = _load_file_hooks()

    assert len(hooks) == 1
    assert hooks[0].filters.path_globs == ("final/**/*.md",)
    assert hooks[0].filters.producers == ("commit", "sdd", "finalizer")


def test_spec_literals_match_schema_version_1() -> None:
    assert RESEARCH_REF_PROVIDER_SPEC["schema_version"] == 1
    assert RESEARCH_HIGHLIGHTS_HOOK_SPEC["schema_version"] == 1
    assert RESEARCH_HIGHLIGHTS_HOOK_SPEC["required"] == ["command"]
    assert "command" not in RESEARCH_HIGHLIGHTS_HOOK_SPEC["file_hook"]


def test_research_ref_expansion_format_is_a_pointer_not_path_bound() -> None:
    from sase.artifact_ref_operations import artifact_ref_expansion_validate

    expansion_format = RESEARCH_REF_PROVIDER_SPEC["ref"]["expansion_format"]

    assert (
        expansion_format
        == "the {repo_relative_path} file in the {sidecar_role} sidecar repo"
    )
    placeholders = set(artifact_ref_expansion_validate(expansion_format))
    assert "checkout_path" not in placeholders
