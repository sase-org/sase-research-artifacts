# sase-research-artifacts

`sase-research-artifacts` is an installable Python plugin for
[sase](https://github.com/sase-org/sase) that ships the `research`
artifact-reference provider, the `research-highlights` file-hook provider, the
`#research*` xprompts, and default model/tribe config for research workflows.
Durable research reports and generated media live in the
[`sase-org/sase--research`](https://github.com/sase-org/sase--research) sidecar; this
plugin supplies the SASE integrations that make those artifacts discoverable and
usable from agent workflows.

## Installation

Requires Python 3.12+, `sase>=0.17.2`, and `sase-core-rs>=0.34.23,<0.35.0`. See
[docs/configuration.md](docs/configuration.md#requirements).

```bash
pip install sase-research-artifacts
```

Installing the distribution registers four entry points that sase discovers
automatically; a linked-repo clone alone does not install the package or register its
entry points.

## Entry points

| Group                | Name                      | Target                                                        |
| -------------------- | ------------------------- | ------------------------------------------------------------- |
| `sase_artifact_refs` | `research`                | `sase_research_artifacts.provider:RESEARCH_REF_PROVIDER`      |
| `sase_file_hooks`    | `research-highlights`     | `sase_research_artifacts.provider:RESEARCH_HIGHLIGHTS_HOOK`   |
| `sase_xprompts`      | `sase_research_artifacts` | `sase_research_artifacts`                                     |
| `sase_config`        | `sase_research_artifacts` | `sase_research_artifacts`                                     |

## Provider configuration

Point a project's `research` sidecar role at this plugin's ref provider with one line:

```yaml
repos:
  sidecar:
    custom:
      research:
        ref:
          use: sase-research-artifacts@research
```

Wire the file hook the same way, supplying the one field the provider deliberately
leaves unset -- the actual command is local to your machine:

```yaml
file_hooks:
  - use: sase-research-artifacts@research-highlights
    command: bob highlights create --include-id
```

Both `use:` and a fully inline spec normalize to the same effective policy; overriding
individual fields (e.g. `inventory.globs`) deep-merges over the provider's base spec,
with list-valued fields replacing rather than concatenating.

### The `research` ref provider

Schema version 1, kind `research`. Inventory starts with `20*/**/*.md` (every dated
report, including `__cdx`/`__cld`/`__grk`/`__mus` swarm drafts) and excludes generated infographic
companion Markdown such as `*_infographic.md` and disambiguated binary pages such as
`*.png.md`. Declared frontmatter properties: `create_time` and `updated_time`
(datetime), `status` (enum: `draft`, `review`, `final`, `archived`), `tags` (string
list). The provider also declares its Artifacts pane label, row fields, updated-time
descending sort, status/tags facets, status grouping, and Research-specific empty copy.
Publication links to the VCS permalink and writes a `Referenced By` table back into
cited reports.

### The `research-highlights` file hook

Renders new committed research reports into Highlights PDFs for the Obsidian reading
queue. Restricted to the `research` sidecar, producers `commit`, `sdd`, and
`finalizer`, `ADD` operations only, and excludes agents matching `research.*.cld` /
`research.*.cdx` (the swarm's own participants) plus `__cdx`/`__cld`/`__grk`/`__mus`
draft files -- a
Highlights PDF is only wanted for the consolidated report, not each researcher's draft.
Artifact-copy events are deliberately excluded because detached artifact execution uses
durable content-addressed paths whose basenames may include digest suffixes; Bob derives
its PDF basename and marker id from the input Markdown basename.

**The two glob sets differ on purpose.** The ref provider's inventory keeps swarm drafts
because citing a specific researcher's draft with `@research:...` is legitimate; the file
hook excludes them because a Highlights PDF per draft is noise. This is not a porting bug.

`command` is intentionally left unset in the packaged template and marked `required`, so
`use: sase-research-artifacts@research-highlights` without a local `command:` override fails soft with a
diagnostic rather than running someone else's command on your machine.

## Xprompts

- `#research` -- write research to a new dated file in the `research` artifact repo.
- `#research/image` -- generate an infographic from a research file's main points.
- `#research/more` -- extend a research file with further research, filling gaps.
- `#research/prompt` -- research prior art and alternatives for a prompt, then `#research`
  it.
- `#research_swarm` -- launch up to four per-provider independent researchers plus an
  always-run lead who consolidates their reports; codex + claude researchers plus the
  lead by default (three agents), grok and muse opt-in via `grok=true` / `muse=true`,
  or four agents with the default set when `should_generate_image=true` opts into the
  infographic segment. A provider that is temporarily disabled drops its researcher
  even when requested. Optional `wait` names agent(s) researchers should wait on
  before starting; quote the value when listing several (`wait="a,b"`). Each launched
  segment requests `0.25` runner capacity units by default. `runners` is an optional
  positive-integer capacity budget with no default; when supplied, it applies as
  `capacity=N` to every launched agent. SASE rejects authored `capacity=0`. Optional
  `priority` is an integer with no default override: a supplied value applies to every
  launched agent (lower values start first); omission uses SASE's implicit queue
  priority. Optional `codex_model`, `claude_model`, `grok_model`, `muse_model`, and
  `lead_model` choose the `.cdx`, `.cld`, `.grk`, `.mus`, and `.final` agent models,
  defaulting to `codex/gpt-5.6-sol@xhigh`, `claude/opus@xhigh`, `grok/grok-4.6@xhigh`,
  `muse/muse-spark-1.3-contributor@xhigh` (carries SASE's `warn` advisory), and
  `@xlarge`.
  Example: `#research_swarm(codex_model=@codex, claude_model=@opus,
  lead_model=@xlarge): compare approaches`.
  Image example:
  `#research_swarm(prompt="A research topic", should_generate_image=true)`.
  Provider gating needs a host sase that ships the `provider_enabled` /
  `provider_disabled` prompt filters.

## Defaults

`default_config.yml` ships the `image` model alias, the `researchers` bucket, and the
`research` tribe display config. By default, `#research_swarm` uses concrete
per-provider models for the codex, claude, grok, and muse researchers, this plugin's
`image` alias for the opt-in image agent, and SASE's built-in `@xlarge` alias for the
lead segment, so the swarm works out of the box on a fresh install. Project or user
config still overrides aliases by normal layer precedence, and callers can override
each researcher role model per invocation.

## Development

```bash
just install    # Install in editable mode with dev deps
just lint       # ruff check + mypy
just fmt        # Auto-format
just test       # pytest (excludes the slow wheel contract test)
just test-wheel # Build a real wheel, install it fresh, verify entry points/resources
just check      # lint + test
```

`just install` and CI both build against coordinated sibling `sase` and `sase-core`
source checkouts so prompt-template changes can exercise the matching host runtime. The
publish workflow also runs a clean wheel-only smoke against exact published SASE and
core floors before uploading this plugin.

## Documentation

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [XPrompts](docs/xprompts.md)

## License

MIT
