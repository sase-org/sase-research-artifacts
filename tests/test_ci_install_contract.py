"""Static assertions on the CI/Justfile coordinated-source wiring.

These check the *shape* of the workflow/Justfile text (sibling checkouts,
python-version matrix, overrides-file usage) so an edit that silently drops
the coordinated-source lane fails fast without needing to run CI itself.
"""

from __future__ import annotations

from importlib.metadata import requires
from pathlib import Path
import tomllib

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_CORE_REQUIREMENT = "sase-core-rs>=0.34.23,<0.35.0"
PUBLISHED_MINIMUM_SASE = "sase==0.17.2"
PUBLISHED_MINIMUM_CORE = "sase-core-rs==0.34.23"
INCOMPATIBLE_SASE = "sase==0.17.1"
INCOMPATIBLE_CORE = "sase-core-rs==0.33.0"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def _core_specifier(raw_requirements: list[str]) -> SpecifierSet:
    for raw in raw_requirements:
        requirement = Requirement(raw)
        if canonicalize_name(requirement.name) == "sase-core-rs":
            return requirement.specifier
    raise AssertionError("missing sase-core-rs requirement")


def _inclusive_lower_bound(spec: SpecifierSet) -> Version:
    floors = [Version(item.version) for item in spec if item.operator in {">=", "=="}]
    assert floors, spec
    return min(floors)


def test_ci_builds_coordinated_sase_sources() -> None:
    workflow = _read(".github/workflows/ci.yml")

    assert workflow.count("repository: sase-org/sase\n") == 1
    assert workflow.count("repository: sase-org/sase-core\n") == 1
    assert "uses: dtolnay/rust-toolchain@stable" in workflow
    assert 'python-version: ["3.12", "3.13"]' in workflow
    assert "uv venv --python ${{ matrix.python-version }} .venv" in workflow
    assert "run: just install" in workflow


def test_justfile_requires_both_source_overrides_together() -> None:
    justfile = _read("Justfile")

    assert "SASE_RESEARCH_ARTIFACTS_SASE_SOURCE_DIR" in justfile
    assert "SASE_RESEARCH_ARTIFACTS_SASE_CORE_SOURCE_DIR" in justfile
    assert "crates/sase_core_py" in justfile
    assert "develop --release" in justfile
    assert "maturin" in justfile
    assert "PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1" in justfile
    assert "--overrides" in justfile
    assert "install-source-sase" in justfile


def test_pyproject_floor_matches_expected_first_supporting_release() -> None:
    pyproject = _read("pyproject.toml")

    assert "dependencies = [" in pyproject
    assert '"sase>=0.17.2"' in pyproject
    assert f'"{PLUGIN_CORE_REQUIREMENT}"' in pyproject


def test_release_smoke_builds_coordinated_sase_sources_and_uses_overrides() -> None:
    workflow = _read(".github/workflows/publish.yml")
    smoke_job = workflow.split("  install-smoke:\n", maxsplit=1)[1].split(
        "  publish:\n", maxsplit=1
    )[0]

    assert "repository: sase-org/sase\n" in smoke_job
    assert "repository: sase-org/sase-core\n" in smoke_job
    assert "uses: dtolnay/rust-toolchain@stable" in smoke_job
    assert "--overrides /tmp/sase-overrides.txt dist/*.whl" in smoke_job
    assert "just install-source-sase /tmp/smoke-venv/bin/python" in smoke_job
    assert smoke_job.index("dist/*.whl") < smoke_job.index("install-source-sase")


def test_release_smoke_requires_clean_published_minimum_wheels() -> None:
    workflow = _read(".github/workflows/publish.yml")
    published_smoke = workflow.split(
        "  install-smoke-published-minimum:\n", maxsplit=1
    )[1].split("  publish:\n", maxsplit=1)[0]
    publish_job = workflow.split("  publish:\n", maxsplit=1)[1]

    assert "install-smoke-published-minimum" in publish_job
    assert f'"{PUBLISHED_MINIMUM_SASE}"' in published_smoke
    assert f'"{PUBLISHED_MINIMUM_CORE}"' in published_smoke
    assert "--overrides" not in published_smoke
    assert "install-source-sase" not in published_smoke
    assert "maturin" not in published_smoke
    assert "load_xprompts_from_plugins" in published_smoke
    assert "expand_single_xprompt" in published_smoke
    assert "plan_typed_launch_units" in published_smoke
    assert 'selected_project="sase"' in published_smoke
    assert "directives.queue_capacity" in published_smoke
    assert "capacity=" in published_smoke
    assert "at least 1" in published_smoke
    assert '{"runners": "0"}' in published_smoke
    assert '{"runners": "1"}' in published_smoke
    assert "runner_capacity_policy_schema_version" in published_smoke
    assert INCOMPATIBLE_SASE in published_smoke
    assert "Refuse older published SASE" in published_smoke
    assert f'"{INCOMPATIBLE_CORE}"' in published_smoke
    assert "Refuse older published core" in published_smoke


def test_wheel_contract_is_source_coordination_not_published_minimum() -> None:
    wheel_test = _read("tests/test_wheel_contract.py")
    justfile = _read("Justfile")

    assert "SASE_RESEARCH_ARTIFACTS_RESOLVED_SASE_SOURCE" in wheel_test
    assert "maturin" in wheel_test
    assert 'startswith("0.34.")' in wheel_test
    assert "plan_typed_launch_units" in wheel_test
    assert 'selected_project="sase"' in wheel_test
    assert "at least 1" in wheel_test
    assert PUBLISHED_MINIMUM_SASE not in wheel_test
    assert PUBLISHED_MINIMUM_CORE not in wheel_test
    assert "source-coordination" in justfile.lower()
    assert "published-minimum" in justfile.lower()


def test_plugin_core_window_accepts_installed_sase_floor() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    plugin_core = _core_specifier(list(pyproject["project"]["dependencies"]))
    assert Version("0.34.23") in plugin_core
    assert Version("0.34.24") in plugin_core
    assert Version("0.33.0") not in plugin_core
    assert Version("0.35.0") not in plugin_core

    sase_core = _core_specifier(list(requires("sase") or []))
    sase_floor = _inclusive_lower_bound(sase_core)
    assert sase_floor in plugin_core, (sase_floor, plugin_core, sase_core)
    assert sase_floor in sase_core


def test_entry_points_declared_once_each_to_avoid_double_registration() -> None:
    pyproject = _read("pyproject.toml")

    assert pyproject.count('[project.entry-points."sase_artifact_refs"]') == 1
    assert pyproject.count('[project.entry-points."sase_file_hooks"]') == 1
    assert "RESEARCH_REF_PROVIDER" in pyproject
    assert "RESEARCH_HIGHLIGHTS_HOOK" in pyproject
