"""bob-cli is a personal tool and must never become a dependency of this plugin."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOB = re.compile(r"\bbob\b", re.IGNORECASE)


def test_plugin_sources_and_docs_do_not_depend_on_bob() -> None:
    paths = [
        *ROOT.joinpath("src/sase_research_artifacts").rglob("*"),
        *ROOT.joinpath("docs").rglob("*"),
        ROOT / "README.md",
        ROOT / "AGENTS.md",
    ]
    matches = []
    for path in paths:
        if not path.is_file():
            continue
        for line_number, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
            if BOB.search(line):
                matches.append(f"{path.relative_to(ROOT)}:{line_number}: {line}")
    assert not matches, "\n".join(matches)
