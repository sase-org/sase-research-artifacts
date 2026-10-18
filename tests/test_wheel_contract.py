"""Build a real sdist/wheel and prove packaged resources survive it.

This is the source-coordination lane: it installs the built plugin wheel with
a local SASE checkout override and a maturin-built sase-core-rs. It is not
published-minimum acceptance. Marked ``wheel`` (excluded from the default
``-m "not wheel"`` lane; run via ``just test-wheel``) since it builds a wheel
and a fresh sase-core-rs from source, which takes minutes rather than seconds.
"""

from __future__ import annotations

from email.parser import Parser
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION_NAME = "sase-research-artifacts"
PACKAGE_NAME = "sase_research_artifacts"
MINIMUM_SASE_VERSION = "0.18.0"
MINIMUM_SASE_CORE_RS_VERSION = "0.35.0"

pytestmark = pytest.mark.wheel


def _single_artifact(dist_dir: Path, pattern: str) -> Path:
    artifacts = list(dist_dir.glob(pattern))
    assert len(artifacts) == 1, artifacts
    return artifacts[0]


def _resolved_source_dir(env_var: str) -> str:
    value = os.environ.get(env_var)
    if not value:
        pytest.skip(
            f"{env_var} is not set; run this test via `just test-wheel`, which "
            "exports the resolved coordinated-source paths"
        )
    return value


@pytest.fixture(scope="module")
def built_distributions(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dist_dir = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist_dir)],
        cwd=ROOT,
        check=True,
    )
    return dist_dir


def test_distribution_artifacts_use_renamed_identity(
    built_distributions: Path,
) -> None:
    wheel = _single_artifact(built_distributions, "*.whl")
    sdist = _single_artifact(built_distributions, "*.tar.gz")

    assert wheel.name.startswith(f"{PACKAGE_NAME}-")
    assert sdist.name.startswith(f"{PACKAGE_NAME}-")

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_path = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(archive.read(metadata_path).decode())

    assert metadata_path.startswith(f"{PACKAGE_NAME}-")
    assert metadata["Name"] == DISTRIBUTION_NAME
    requires_dist = metadata.get_all("Requires-Dist") or []
    assert any(
        requirement.startswith(f"sase>={MINIMUM_SASE_VERSION}")
        for requirement in requires_dist
    )
    assert any(
        requirement.startswith("sase-core-rs")
        and f">={MINIMUM_SASE_CORE_RS_VERSION}" in requirement
        and "<" not in requirement
        for requirement in requires_dist
    )
    # Guard against accidentally carrying a compatibility package under the old name.
    assert all("sase_research/" not in name for name in names)


def test_wheel_contains_provider_defaults_and_all_seven_macros(
    built_distributions: Path,
) -> None:
    wheel = _single_artifact(built_distributions, "*.whl")

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())

    assert f"{PACKAGE_NAME}/provider.py" in names
    assert f"{PACKAGE_NAME}/default_config.yml" in names
    assert f"{PACKAGE_NAME}/input_types.yml" in names
    # The packaged directory keeps its `xprompts/` name during the transition.
    for macro in (
        "research.md",
        "research_audio.md",
        "research_diagrams.md",
        "research_image.md",
        "research_more.md",
        "research_prompt.md",
        "research_swarm.md",
    ):
        assert f"{PACKAGE_NAME}/xprompts/{macro}" in names


def test_sdist_contains_provider_defaults_and_all_seven_macros(
    built_distributions: Path,
) -> None:
    sdist = _single_artifact(built_distributions, "*.tar.gz")

    with tarfile.open(sdist) as archive:
        members = archive.getnames()
        names = {Path(member).name for member in members}

    assert all(member.startswith(f"{PACKAGE_NAME}-") for member in members)
    # Guard against accidentally carrying a compatibility package under the old name.
    assert all("src/sase_research/" not in member for member in members)
    assert "provider.py" in names
    assert "default_config.yml" in names
    assert "input_types.yml" in names
    for macro in (
        "research.md",
        "research_audio.md",
        "research_diagrams.md",
        "research_image.md",
        "research_more.md",
        "research_prompt.md",
        "research_swarm.md",
    ):
        assert macro in names


def test_wheel_installs_into_fresh_venv_with_discoverable_entry_points(
    built_distributions: Path, tmp_path: Path
) -> None:
    sase_source = _resolved_source_dir("SASE_RESEARCH_ARTIFACTS_RESOLVED_SASE_SOURCE")
    sase_core_source = _resolved_source_dir(
        "SASE_RESEARCH_ARTIFACTS_RESOLVED_SASE_CORE_SOURCE"
    )

    wheel = _single_artifact(built_distributions, "*.whl")

    venv_dir = tmp_path / "smoke-venv"
    subprocess.run(["uv", "venv", "--python", "3.12", str(venv_dir)], check=True)
    venv_python = venv_dir / "bin" / "python"

    overrides_file = tmp_path / "sase-overrides.txt"
    overrides_file.write_text(f"-e {sase_source}\n")
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv_python),
            "--overrides",
            str(overrides_file),
            str(wheel),
        ],
        check=True,
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv_python),
            "--no-deps",
            "-e",
            sase_source,
        ],
        check=True,
    )
    subprocess.run(
        ["uv", "pip", "install", "--python", str(venv_python), "maturin"],
        check=True,
    )
    subprocess.run(
        [
            str(venv_dir / "bin" / "maturin"),
            "develop",
            "--release",
        ],
        cwd=Path(sase_core_source) / "crates" / "sase_core_py",
        env={
            **os.environ,
            "VIRTUAL_ENV": str(venv_dir),
            "PYO3_USE_ABI3_FORWARD_COMPATIBILITY": "1",
        },
        check=True,
    )

    # Run the smoke with an isolated SASE_HOME so machine-wide provider
    # disables cannot change the expanded segment counts (mirrors the
    # fast lane's `_isolated_sase_home` fixture). `-I` keeps the script
    # directory off sys.path and ignores PYTHON* variables, so only the
    # installed wheel can satisfy the imports.
    smoke_home = tmp_path / "smoke-home"
    smoke_home.mkdir(exist_ok=True)
    result = subprocess.run(
        [str(venv_python), "-I", str(ROOT / "tests" / "wheel_smoke.py")],
        capture_output=True,
        text=True,
        env={**os.environ, "SASE_HOME": str(smoke_home)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WHEEL_CONTRACT_OK" in result.stdout
