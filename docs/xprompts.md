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
`<stem>_infographic.png` alongside the source file, where `<stem>` is the source
file's stem with any trailing `__final` removed (so `topic__final.md` becomes
`topic_infographic.png`).

## `#research/audio` -- Narrate an Audio Edition

Narrates a research report as a chaptered MP3 audio edition. Requires
`uv tool install sase-listen`: the xprompt drives the installed CLI (`guide` to
author the script, `lint --source` to check it, `render --json` to synthesize it)
and never depends on it as a package.

### Input

| Name      | Type | Default | Description                                              |
| --------- | ---- | ------- | -------------------------------------------------------- |
| `edition` | word | `full`  | Narration edition budget: `full`, `brief`, `digest`, or `verbatim` |
| `rewrite` | bool | `false` | Rewrite `<stem>_narration.md` even when one already exists |

When invoked with a `@research:` ref the report is read with `sase artifact read`;
when forked from a swarm lead the agent uses the report it wrote, preferring the
published `<name>.md` and falling back to `<name>__final.md`. The narration script
is `<stem>_narration.md` next to the report (with `__final` stripped from the stem,
following the `#research/image` stem rule) and carries `source`, `source_blob`,
`date`, `kind: research`, and `cover` when `<stem>_infographic.png` exists. The
finished MP3 is registered with
`sase artifact create -p <audio_path> -l "Audio edition: <title>"` so it rides the
completion notification to Telegram.

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
| `runners`               | int  | `null`                                  | Optional positive-integer capacity budget replacing `1.5x` |
| `codex`                 | bool | `true`                                  | Request the codex researcher                             |
| `claude`                | bool | `true`                                  | Request the claude researcher                            |
| `grok`                  | bool | `false`                                 | Request the grok researcher                              |
| `muse`                  | bool | `false`                                 | Request the muse researcher                              |
| `gemini`                | bool | `false`                                 | Request the gemini (Antigravity) researcher              |
| `codex_model`           | word | `codex/gpt-6.1-sol@xhigh`               | Model for `<clan>.cdx`                                   |
| `claude_model`          | word | `claude/opus@xhigh`                     | Model for `<clan>.cld`                                   |
| `grok_model`            | word | `grok/grok-4.6@xhigh`                   | Model for `<clan>.grk`                                   |
| `muse_model`            | word | `muse/muse-spark-1.3-contributor@xhigh` | Model for `<clan>.mus` (carries SASE's `warn` advisory)  |
| `gemini_model`          | word | `agy/gemini-3.8-flash-high`             | Model for `<clan>.gem`; no `@effort` suffix              |
| `lead_model`            | word | `@xlarge`                               | Model for `<clan>.final`                                 |
| `image`                 | bool | `false`                                 | Opt into `<clan>.image` (implies the linker)             |
| `image_model`           | word | `@image`                                | Model for `<clan>.image`                                 |
| `linker`                | bool | `false`                                 | Opt into `<clan>.linker` (always runs with `image=true`) |
| `linker_model`          | word | `@xlarge`                               | Model for `<clan>.linker`                                |
| `audio`                 | bool | `false`                                 | Opt into `<clan>.audio` (never implies the linker)       |
| `audio_model`           | word | `@audio`                                | Model for `<clan>.audio`                                 |

Quote `wait` when passing several comma-separated agents (`wait="a,b"`); an unquoted
comma is parsed as a separate xprompt argument.

A three-agent xprompt swarm by default (codex + claude researchers plus the lead), up
to nine authored segments (five researchers, the lead, the image agent, the linker
agent, the audio agent). `grok=true` /
`muse=true` / `gemini=true` each add a researcher; `codex=false` (or any provider flag
`false`) drops one; turning all five off leaves exactly the lead running solo. A
provider that is hard-disabled drops its researcher even when its boolean input
is true; a soft-disabled provider still runs its researcher (soft disables never
refuse explicit model launches). When `image=true` opts into the image segment, the default set
runs five agents, because image implies linker. Optional `wait` gates only the researchers. Optional `priority`
applies to every launched agent when supplied (lower values start first); omission uses
SASE's implicit queue priority. Every launched segment authors `%q(1.5x, w=0.25)`,
so each member's capacity budget is 1.5 times this machine's effective
`max_running_agents` budget (7.5 capacity units when the effective budget is 5).
The image opt-in and the linker opt-in author the same directive on their segments.
`runners` has no default; when supplied, it replaces the `1.5x` multiplier with an
absolute budget `N` on every segment without changing the `0.25` weight. `N` must be
a positive integer (`1` is the smallest valid budget; four quarter-weight members fit
in it, while all five researchers plus the lead -- six quarter-weight members --
need a budget of at least 2 to run concurrently). Explicit `runners=0` still renders
as `%q(0, w=0.25)` on every launched segment, and SASE rejects that authored value at launch.
The nine model inputs can be supplied independently, for example
`#research_swarm(codex_model=@codex, claude_model=@opus, lead_model=@xlarge): ...`.
Omitting them preserves the defaults below. The opt-in image segment uses
`image_model` (default `@image`), for example
`#research_swarm(prompt="A research topic", image=true)`.
The opt-in linker segment uses `linker_model` (default `@xlarge`), for example
`#research_swarm(prompt="A research topic", linker=true)`.
The opt-in audio segment uses `audio_model` (default `@audio`), for example
`#research_swarm(prompt="A research topic", audio=true)`.
The `muse-spark-1.3-contributor` default carries SASE's `warn` model advisory
("trains on your data"), which is part of why `muse` defaults off. The `agy`
provider rejects explicit `@effort` suffixes, so the `gemini_model` default carries
no effort suffix and effort is chosen via the model slug (`-high`/`-medium`/`-low`).

1. **`<clan>.cdx`** -- the codex researcher (`codex/gpt-6.1-sol@xhigh`), writing a
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
5. **`<clan>.gem`** -- the gemini (Antigravity) researcher
   (`agy/gemini-3.8-flash-high`), opt-in via `gemini=true`, writing via
   `#research(suffix=gem)`. Antigravity (`agy`) rejects explicit `@effort` suffixes,
   so effort is chosen through the model slug (`-high`/`-medium`/`-low`).
6. **`<clan>.final`** -- the lead researcher (`@xlarge`), waiting on every surviving
   researcher (no waits when none ran, running solo instead), who reads the registered
   reports, does further research, and writes a consolidated report merging every
   perspective. Individual researcher reports move to `<name>__<short>.md` under
   `<name>/`, preserving each report's existing suffix; the consolidated report is
   `<name>/<name>.md`. Carries the clan's tribe/summary declaration.
7. **`<clan>.image`** -- optional; when `image=true`, waits on and forks
   from the lead's segment, then runs `#research/image` against the lead's
   `<name>__final.md` using `image_model` (default `@image`).
8. **`<clan>.linker`** -- optional; runs when `linker=true`, and always when
   `image=true`. Waits on the lead (and on the image agent when `image=true`)
   without forking, finds the lead's `<name>__final.md` through `wait.artifacts`,
   and writes and registers the canonical, well-structured `<name>.md`. The file
   opens with the title, then a short research-query summary of the swarm's `prompt`,
   then the infographic when one was generated, then the `## Bottom line` /
   `## Overview` section. Restructured sections with checked links and in-document
   jump links follow.
9. **`<clan>.audio`** -- optional; when `audio=true`, waits on the lead (and on the
   linker when it runs, so the edition narrates the published `<name>.md` and can
   use the infographic as its cover), forks from the lead's segment, then runs
   `#research/audio` using `audio_model` (default `@audio`). `audio=true` never
   implies the linker. Requires `uv tool install sase-listen`.

The handoff contract: the lead writes `<name>__final.md` (instead of `<name>.md`) and
registers it only when the linker runs, and the linker derives its output directory
from that registered label rather than the current date. The linker is an editor, not
a researcher: it must not add claims or sources, and it leaves the lead's report as
written when it disagrees with it.

Execution matrix (default researchers cdx + cld):

| `linker` | `image` | Agents               | Lead writes                    | Hook fires on                                    |
| -------- | ------- | -------------------- | ------------------------------ | ------------------------------------------------ |
| false    | false   | cdx, cld, final (3)  | `<name>.md`, unregistered      | lead's `<name>.md` (byte-identical to before)    |
| true     | false   | + linker (4)         | `<name>__final.md`, registered | linker's `<name>.md`                             |
| false    | true    | + image + linker (5) | `<name>__final.md`, registered | linker's `<name>.md`                             |
| true     | true    | + image + linker (5) | `<name>__final.md`, registered | linker's `<name>.md`                             |

Image implies linker: only the linker's `<name>.md` is hook-eligible, so the
Highlights PDF is rendered after the infographic exists.

`audio=true` adds one `<clan>.audio` agent to every matrix row above and writes
`<name>_narration.md` beside the report; the lead's output, the hook target, and
the rest of each row are unchanged. The narration script is excluded from both the
`@research` inventory and the Highlights hook, like the infographic companion
pages.

Image failure recovery: named waits release only on completion, so a failed image
agent leaves the linker parked with no `<name>.md` and no PDF (SASE posts a "Wait
dependency can never self-resolve" notification). A later successful run of the same
`research.<N>.image` name releases the parked linker; alternatively, kill the parked
linker. `<name>__final.md` stays in the repo either way. If the image agent completes
without producing a PNG, the linker publishes without it and says so.

Setting `image_model` to a single model gives up the `@image` alias's fallback chain
across providers.

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
and prints each entry's `wait_name`, `label`, `source_path`, `path`, and durable `ref`
as plain `key=value` text: the deferred loop renders in sase's launch-time
top-level pass, where inline code is literal and would leave `{{ ... }}`
unrendered. The `__` in labels and paths still survives, because sase's
agent-prompt formatter preserves `_` and `*` literals. The lead matches each `wait_name` to the
`__<suffix>.md` suffix already on the label,
never by list order, then reads each report through its canonical research reference
(or the `ref` fallback) with `sase artifact read`.

By default this depends on the `image` and `audio` model aliases and the `researchers`
bucket from
this plugin's default config, plus SASE's built-in `@xlarge` alias for the lead and
linker segments. Provider gating needs a host sase that ships the mode-aware `provider_enabled("hard")` /
`provider_disabled` prompt filters.
