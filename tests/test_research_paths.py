from pathlib import Path


XPROMPT_DIR = Path(__file__).parents[1] / "src" / "sase_research_artifacts" / "xprompts"


def test_research_xprompts_resolve_checkout_at_agent_runtime() -> None:
    sources = {
        path.stem: path.read_text(encoding="utf-8") for path in XPROMPT_DIR.glob("*.md")
    }

    assert sources
    assert all("sase repo path" not in source for source in sources.values())
    assert "sase repo open research" in sources["research"]
    assert "sase repo open research" in sources["research_swarm"]
