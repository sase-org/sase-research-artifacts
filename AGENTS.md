# sase-research-artifacts - Agent Instructions

## Overview

Research artifact-reference, file-hook, config, and xprompt provider plugin for sase.
It integrates the `sase-org/sase--research` sidecar by contributing the `research`
artifact-reference provider, `research-highlights` file hook, default research model
aliases, and `#research*` xprompts.

## Build & Run

```bash
just install    # Install in editable mode with dev deps
just lint       # ruff check + mypy
just fmt        # Auto-format
just test       # pytest (excludes the slow wheel contract test)
just test-wheel # Build a real wheel, install it fresh, verify entry points/resources
just check      # lint + test
```

## Architecture

- `src/sase_research_artifacts/provider.py` — the `research` artifact-ref provider spec
  (`RESEARCH_REF_PROVIDER`) and the `research-highlights` file-hook provider spec
  (`RESEARCH_HIGHLIGHTS_HOOK`), each a pluggy hookimpl object registered under its own
  `sase_artifact_refs` / `sase_file_hooks` entry point.
- `src/sase_research_artifacts/xprompts/` — the `#research`, `#research/image`,
  `#research/more`, `#research/prompt`, and `#research_swarm` xprompts, discovered
  through the `sase_xprompts` entry point.
- `src/sase_research_artifacts/default_config.yml` — the `image` default model alias,
  the `researchers` bucket, and the `research` tribe display config, discovered
  through the `sase_config` entry point. The research-swarm researchers default to
  concrete per-provider models and the lead defaults to SASE's built-in `@xlarge`
  alias; the optional critique agent, like the lead, defaults to SASE's built-in
  `@xlarge` alias. Provider gating needs a host sase that ships the mode-aware `provider_enabled("hard")` /
  `provider_disabled` prompt filters; revisit the `sase` floor in `pyproject.toml`
  when a release actually carries them.
- Depends on `sase>=0.17.2` and `sase-core-rs>=0.34.23,<0.35.0`; the `sase` floor is
  the first release line expected to carry unconditional weighted queue support, and
  the core window matches current SASE.

## Code Conventions

- Absolute imports: `from sase_research_artifacts.provider import RESEARCH_REF_PROVIDER`
- Target Python 3.12+
- Follow ruff rules matching sase core
- Register a hookimpl object under exactly one of `sase_artifact_refs` /
  `sase_file_hooks` even if a class implements both hookspec methods — the registry
  calls both hooks on every discovered plugin regardless of which group found it, so
  dual-registration double-collects specs.
