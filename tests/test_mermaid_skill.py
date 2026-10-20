"""Contract checks for the Mermaid skill's shipped measurement command."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest


def _skill_text() -> str:
    return (
        importlib.resources.files("sase_research_artifacts")
        .joinpath("skills", "mermaid_diagrams.md")
        .read_text(encoding="utf-8")
    )


def _measurement_script() -> str:
    match = re.search(
        r'python3 - "\$scratch/figure\.svg" <<\'PY\'\n(.*?)\nPY\n```',
        _skill_text(),
        re.DOTALL,
    )
    assert match, "the shipped render recipe must contain its measurement command"
    return match.group(1)


def _measure(tmp_path: Path, svg_text: str) -> subprocess.CompletedProcess[str]:
    svg_path = tmp_path / "figure.svg"
    svg_path.write_text(svg_text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", _measurement_script(), str(svg_path)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("diagram", "svg", "expected"),
    [
        (
            "flowchart",
            '<svg width="603" height="600" viewBox="0 0 603 600"/>',
            "603×600 px, fit 100.0%",
        ),
        (
            "state",
            '<svg width="500px" height="800px" viewBox="0 0 500 800"/>',
            "500×800 px, fit 100.0%",
        ),
        (
            "sequence",
            '<svg width="100%" height="900" viewBox="0 0 700 900"/>',
            "700×900 px, fit 93.3%",
        ),
    ],
)
def test_shipped_measurement_command_reads_diagram_dimensions(
    tmp_path: Path,
    diagram: str,
    svg: str,
    expected: str,
) -> None:
    result = _measure(tmp_path, svg)
    assert result.returncode == 0, f"{diagram}: {result.stdout}{result.stderr}"
    assert expected in result.stdout


def test_shipped_measurement_command_fails_visibly_below_fit_floor(
    tmp_path: Path,
) -> None:
    result = _measure(tmp_path, '<svg width="1000" height="1200"/>')
    assert result.returncode == 1
    assert "FAIL: 1000×1200 px, fit 65.3% (below 75%)" in result.stdout


def test_shipped_measurement_command_rejects_unusable_dimensions(
    tmp_path: Path,
) -> None:
    result = _measure(tmp_path, '<svg width="auto" height="0"/>')
    assert result.returncode != 0
    assert "FAIL: SVG has no usable positive pixel dimensions or viewBox" in result.stderr


def test_skill_pins_the_renderer_and_fit_contract() -> None:
    skill = _skill_text()

    assert "mktemp -d /tmp/mmd.XXXXXX" in skill
    config_match = re.search(
        r'cat >"\$scratch/pdf\.json" <<\'JSON\'\n(.*?)\nJSON',
        skill,
        re.DOTALL,
    )
    assert config_match, "the shipped recipe must include its PDF-mirroring config"
    pdf_config = json.loads(config_match.group(1))
    assert pdf_config["securityLevel"] == "strict"
    assert pdf_config["theme"] == "neutral"
    assert {"themeCSS", "themeVariables", "fontFamily"} <= set(
        pdf_config["secure"]
    )
    assert '"flowchart": { "useMaxWidth": false }' in skill
    assert "npx -y -p @mermaid-js/mermaid-cli@12.0.0 mmdc" in skill
    assert skill.index(
        "try_cli npx -y -p @mermaid-js/mermaid-cli@12.0.0 mmdc"
    ) < skill.index("try_cli mmdc")
    assert '"args":["--no-sandbox"]' in skill
    assert '"${MMDC[@]}" --version' in skill
    assert '"${MMDC[@]}" -c "$scratch/pdf.json" -i figure.mmd -o "$scratch/figure.svg"' in skill
    assert '-o "$scratch/figure.png" -s 1.5 -b white' in skill
    assert "timeout 90s" in skill
    assert "ConnectionClosedError" in skill
    assert "viewBox" in skill
    assert "652.8 / width, 892.8 / height" in skill
    assert "scale < 0.75" in skill
    assert "Open the PNG" in skill
    assert "at most twice" in skill

    for role, fill, stroke, text in (
        ("focus", "#E8F1FB", "#3B78C2", "#0F2E52"),
        ("decision", "#FFF7E6", "#C77C02", "#4A3000"),
        ("outcome", "#E7F5EC", "#2E7D4F", "#123D24"),
        ("risk", "#FDECEC", "#C0392B", "#5F1414"),
        ("muted", "#F3F4F6", "#6B7280", "#1F2937"),
    ):
        assert f"classDef {role} fill:{fill},stroke:{stroke}" in skill
        assert f"color:{text}" in skill
    assert "classDef proposed stroke-dasharray:5 3" in skill
    assert "class NODE muted\nclass NODE proposed" in skill
    assert "`fill:none` and a stroke that matches their class" in skill
    assert "Do not use timeline, pie, mindmap" in skill
    assert "optional invisible `accTitle:` and `accDescr:`" in skill
    assert "wrappingWidth: 260" in skill
