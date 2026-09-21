# XPrompts

## `#research` -- Write Research to a Dated File

Writes the current research to a new markdown file under
`$(sase repo path research --ensure)/$(date +%Y%m)/`.

### Input

| Name            | Type | Description                                                                 |
| --------------- | ---- | --------------------------------------------------------------------------- |
| `report_target` | path | Optional month-relative markdown path to write exactly                      |
| `suffix`        | word | Optional filename suffix requiring `<stem>__<suffix>.md` when used by itself |

When both are supplied, `report_target` wins and names the report file exactly.

After a successful write, `#research` registers the report as a durable snapshot with
`sase artifact create -p "<absolute-report-path>" -l "research:<repo-relative-report-path>"`
(no `--move`). This is the producer contract `#research_swarm`'s lead consumes through
the runtime `wait.artifacts` namespace instead of reading transcripts.

## `#research/image` -- Generate an Infographic

Generates an infographic illustrating a research markdown file's main points, writing
`<source-stem>_infographic.png` alongside the source file.

## `#research/more` -- Extend Existing Research

Extends an existing research markdown file with further research, filling gaps left by
a previous agent, following the research repo's `README.md` conventions when present.

## `#research/prompt` -- Research a Prompt

### Input

| Name     | Type | Description                    |
| -------- | ---- | ------------------------------ |
| `prompt` | text | The prompt or topic to research |

Investigates prior art and alternative solutions for the given prompt, ending with a
recommendation, then hands off to `#research` to write it up.

## `#research_swarm` -- Per-Provider Researchers Plus a Lead

### Input

| Name                    | Type | Default                                 | Description                                              |
| ----------------------- | ---- | --------------------------------------- | -------------------------------------------------------- |
| `prompt`                | text | required                                | Research topic or question for the swarm to investigate  |
| `wait`                  | word | `null`                                  | Optional agent(s) to wait for before the swarm starts    |
| `priority`              | int  | `null`                                  | Optional integer queue priority for every launched agent |
| `runners`               | int  | `null`                                  | Optional positive-integer capacity budget                |
| `codex`                 | bool | `true`                                  | Request the codex researcher                             |
| `claude`                | bool | `true`                                  | Request the claude researcher                            |
| `grok`                  | bool | `false`                                 | Request the grok researcher                              |
| `muse`                  | bool | `false`                                 | Request the muse researcher                              |
| `codex_model`           | word | `codex/gpt-5.6-sol@xhigh`               | Model for `<clan>.cdx`                                   |
| `claude_model`          | word | `claude/opus@xhigh`                     | Model for `<clan>.cld`                                   |
| `grok_model`            | word | `grok/grok-4.6@xhigh`                   | Model for `<clan>.grk`                                   |
| `muse_model`            | word | `muse/muse-spark-1.3-contributor@xhigh` | Model for `<clan>.mus` (carries SASE's `warn` advisory)  |
| `lead_model`            | word | `@xlarge`                               | Model for `<clan>.final`                                 |
| `should_generate_image` | bool | `false`                                 | Opt into `<clan>.image`                                  |

Quote `wait` when passing several comma-separated agents (`wait="a,b"`); an unquoted
comma is parsed as a separate xprompt argument.

A three-agent xprompt swarm by default (codex + claude researchers plus the lead), up
to six authored segments (four researchers, the lead, the image agent). `grok=true` /
`muse=true` each add a researcher; `codex=false` (or any provider flag `false`) drops
one; turning all four off leaves exactly the lead running solo. A provider that is
temporarily disabled drops its researcher even when its boolean input is true. When
`should_generate_image=true` opts into the image segment, the default set runs four
agents. Optional `wait` gates only the researchers. Optional `priority` applies to
every launched agent when supplied (lower values start first); omission uses SASE's
implicit queue priority. Every launched segment authors `%q(w=0.25)`, so the default
swarm consumes `0.75` runner capacity units; the image opt-in consumes one normal unit
when all four members are live.
`runners` has no default; when supplied, it adds `capacity=N` to every segment without
changing the `0.25` weight. `N` must be a positive integer (`capacity=1` is the smallest
valid budget; four quarter-weight members fit in it). Explicit `runners=0` still renders
as `capacity=0` on every launched segment, and SASE rejects that authored value at launch.
The five model inputs can be supplied independently, for example
`#research_swarm(codex_model=@codex, claude_model=@opus, lead_model=@xlarge): ...`.
Omitting them preserves the defaults below. The opt-in image segment always uses
`@image`, for example
`#research_swarm(prompt="A research topic", should_generate_image=true)`.
The `muse-spark-1.3-contributor` default carries SASE's `warn` model advisory
("trains on your data"), which is part of why `muse` defaults off.

1. **`<clan>.cdx`** -- the codex researcher (`codex/gpt-5.6-sol@xhigh`), writing a
   self-named descriptive report via `#research(suffix=cdx)`; when supplied, also waits
   on the `wait` argument's agent(s). Gated by `%if(should_run=...)` on the `codex`
   flag plus the `provider_enabled` filter.
2. **`<clan>.cld`** -- the claude researcher (`claude/opus@xhigh`), run independently
   in parallel, writing a self-named descriptive report via `#research(suffix=cld)`;
   when supplied, also waits on the `wait` argument's agent(s). Gated the same way.
3. **`<clan>.grk`** -- the grok researcher (`grok/grok-4.6@xhigh`), opt-in via
   `grok=true`, writing via `#research(suffix=grk)`.
4. **`<clan>.mus`** -- the muse researcher
   (`muse/muse-spark-1.3-contributor@xhigh`), opt-in via `muse=true`, writing via
   `#research(suffix=mus)`.
5. **`<clan>.final`** -- the lead researcher (`@xlarge`), waiting on every surviving
   researcher (no waits when none ran, running solo instead), who reads the registered
   reports, does further research, and writes a consolidated report merging every
   perspective. Individual researcher reports move to `<name>__<short>.md` under
   `<name>/`, preserving each report's existing suffix; the consolidated report is
   `<name>/<name>.md`. Carries the clan's tribe/summary declaration.
6. **`<clan>.image`** -- optional; when `should_generate_image=true`, waits on and forks
   from the lead's segment, then runs `#research/image` against the consolidated report
   using `@image`.

Each researcher is told the other researchers' agent IDs (`` `research.{@1}.<short>` ``)
and the `__<short>.md` suffix its report filename will end with, and is explicitly
instructed not to seek out or read a peer's report, or its findings indirectly via the
peer's chat transcript, for the duration of the current swarm. With no peers, the
researcher is told it is the only independent researcher. Combining the reports remains
the lead's responsibility.

The lead's prompt no longer reads its predecessors' chat transcripts to discover their
report paths. Instead it renders a raw-protected loop over sase's runtime `wait`
namespace, `wait.artifacts`, which is populated lazily (with one batched query) only
when the lead's prompt actually renders and only lists non-chat artifacts registered by
the researchers. The loop filters to markdown entries whose label carries the canonical
`research:<repo-relative-path>` report reference from `#research`'s registration step,
and prints each entry's `wait_name`, `label`, `source_path`, `path`, and durable `ref`.
The lead matches each `wait_name` to the `__<suffix>.md` suffix already on the label,
never by list order, then reads each report through its canonical research reference
(or the `ref` fallback) with `sase artifact read`.

By default this depends on the `image` model alias and the `researchers` bucket from
this plugin's default config, plus SASE's built-in `@xlarge` alias for the lead
segment. Provider gating needs a host sase that ships the `provider_enabled` /
`provider_disabled` prompt filters.
