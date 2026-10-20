# Architecture

## Plugin System

`sase-research-artifacts` registers five entry points against the host `sase` package.
sase's registry instantiates each discovered entry point once and calls both
`sase_artifact` hookspec methods on it (`artifact_ref_provider_specs`,
`artifact_file_hook_provider_specs`), regardless of which entry-point group discovered
it. Each hookimpl object here implements exactly one of the two methods, so registering
`RESEARCH_REF_PROVIDER` under `sase_artifact_refs` and `RESEARCH_HIGHLIGHTS_HOOK` under
`sase_file_hooks` collects exactly one ref spec and one file-hook spec -- never both
from the same registration.

### Entry Points

| Group                | Name                      | Target                                                        |
| -------------------- | ------------------------- | ------------------------------------------------------------- |
| `sase_artifact_refs` | `research`                | `sase_research_artifacts.provider:RESEARCH_REF_PROVIDER`      |
| `sase_file_hooks`    | `research-highlights`     | `sase_research_artifacts.provider:RESEARCH_HIGHLIGHTS_HOOK`   |
| `sase_macros`        | `sase_research_artifacts` | `sase_research_artifacts` (package, for `xprompts/*.md`)      |
| `sase_xprompts`      | `sase_research_artifacts` | legacy alias of `sase_macros` (same package)                  |
| `sase_config`        | `sase_research_artifacts` | `sase_research_artifacts` (package, for `default_config.yml`) |

### `provider.py`

Two module-level pluggy hookimpl objects, each backed by a plain-dict spec validated by
sase's Rust core at registry-assembly time (`schema_version: 1`):

- `RESEARCH_REF_PROVIDER` implements `artifact_ref_provider_specs`, returning
  `RESEARCH_REF_PROVIDER_SPEC` -- the `research` document ref provider (kind, expansion
  format, typed frontmatter properties, inventory globs, publication policy, and
  declarative Artifacts pane presentation).
- `RESEARCH_HIGHLIGHTS_HOOK` implements `artifact_file_hook_provider_specs`, returning
  `RESEARCH_HIGHLIGHTS_HOOK_SPEC` -- the `research-highlights` file-hook template, with
  `command` deliberately absent and listed in `required`. Its filters include
  `producers: [commit, sdd, finalizer]` so artifact-copy events do not run the
  basename-sensitive local renderer command against content-addressed artifact paths.

Specs are immutable module-level literals, never built per-call: sase's registry calls
these hooks once while assembling the config registry, not per keystroke or per file
event.

## Reference Resolution

A project opts into the `research` ref provider per sidecar role, either with one line
(`ref: {use: sase-research-artifacts@research}`) or a fully inline spec. Both spellings normalize to the same
effective policy -- see `docs/configuration.md`.

## Macro and Default-Config Discovery

`sase_macros` (plus its `sase_xprompts` legacy alias) and `sase_config` are resource
entry-point groups: the entry point resolves to the bare `sase_research_artifacts`
package (no attribute), and sase locates `xprompts/*.md`, `skills/*.md`,
`default_config.yml`, and `input_types.yml` inside it via `importlib.resources`.
`skills/mermaid_diagrams.md` declares `skill: true`, so the plugin skill loader exposes
it both as `/mermaid_diagrams` and as the expandable `#skill/mermaid_diagrams` reference.
The image segment expands the reference once when diagrams run. The lead receives an
on-demand pointer whenever it may author or carry over Mermaid, independent of the
`image` and `diagrams` flags; that pointer does not enable the companion diagrams agent.
When the skill is not deployed, the lead checks
`sase macro show skill/mermaid_diagrams --format raw` (or the slash form) against the
plugin source and uses whichever form the host supports. A same-named home source at
`~/sase/skills/mermaid_diagrams.md` overrides the plugin default under SASE's
first-source-wins skill discovery.

The shared guide gives the complete render and fit contract: use a short `TMPDIR`, the
locked neutral PDF config, and a smoke-tested pinned Mermaid CLI before global `mmdc`;
keep the chosen command and browser flags; render SVG and PNG with the same config; and
measure root SVG dimensions, falling back to `viewBox`, against the 652.8 × 892.8 px
PDF box. Figures below 75% fit fail review. A visual review checks the PNG and source,
allows at most two revisions, and drops a figure that still fails. The producer batch
check keeps its separate five parse-fix rounds and fails open if no CLI is usable.

These resources ship automatically in a hatchling wheel because they live inside
`src/sase_research_artifacts/` and are tracked in git -- no separate package-data
declaration is needed. `input_types.yml` declares the plugin-shared `audio_edition` enum
(`brief` / `full`); macros reference it as `sase-research-artifacts@audio_edition`.
