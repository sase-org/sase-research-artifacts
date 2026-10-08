# Macros

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

Narrates a research report as a chaptered MP3 audio edition with a generated
podcast title card. Requires `sase plugin install listen` (preferred) or
`uv tool install sase-listen` as the alternative: the macro drives
the chosen `<listen>` CLI (`guide` to author the script, `lint --source` to check it,
`render --generated-cover --json` to synthesize it) and never depends on it as
a package. The audio agent prefers `sase listen`, then `sase-listen`, then
`uvx sase-listen`, probing each `render --help` for `--generated-cover`.

### Input

| Name      | Type | Default | Description                                              |
| --------- | ---- | ------- | -------------------------------------------------------- |
| `edition` | `sase-research-artifacts@audio_edition` | `brief` | Narration edition: `brief` or `full` (guide-backed authoring choices) |
| `rewrite` | bool | `false` | Rewrite `<stem>_narration.md` even when one already exists |

Newly authored narration defaults to `brief` (about 4 minutes); pass
`#research/audio(edition=full)` for the full edition (about 16 minutes).
Edition selection affects newly authored narration, not whether audio is
enabled.

When invoked with a `@research:` ref the report is read with `sase artifact read`
and that file is the one narrated. When forked from a swarm lead the agent
narrates the report the lead wrote: `<name>__final.md` when the linker runs,
otherwise the lead's `<name>.md`. Do not poll for a later published file. The
narration script is `<stem>_narration.md` next to the report (with `__final`
stripped from the stem, following the `#research/image` stem rule) and carries
`source`, `source_blob`, `date`, `kind: research`, and `edition`. Newly authored
scripts omit `cover`; reused scripts retain their narration and metadata, with
`<listen> render --generated-cover` overriding any existing artwork. An
existing script is reused unless direct `#research/audio(..., rewrite=true)` is
requested. The finished MP3 is registered
with `sase artifact create -p <audio_path> -k file -l "audio:<episode_id>"` and
the agent sets `sase var set audio` from `render --json`. A failed TTS render
sets `audio.ok=false`, registers no artifact, and completes normally.

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
| `codex_model`           | model | `codex/gpt-6.1-sol@xhigh`               | Model for `<clan>.cdx`                                   |
| `claude_model`          | model | `claude/opus@xhigh`                     | Model for `<clan>.cld`                                   |
| `grok_model`            | model | `grok/grok-4.6@xhigh`                   | Model for `<clan>.grk`                                   |
| `muse_model`            | model | `muse/muse-spark-1.3-contributor@xhigh` | Model for `<clan>.mus` (carries SASE's `warn` advisory)  |
| `gemini_model`          | model | `agy/gemini-3.8-flash-high`             | Model for `<clan>.gem`; no `@effort` suffix              |
| `lead_model`            | model | `@xlarge`                               | Model for `<clan>.final`                                 |
| `image`                 | bool | `false`                                 | Opt into `<clan>.image` (implies the linker)             |
| `image_model`           | model | `@image`                                | Model for `<clan>.image`                                 |
| `linker`                | bool | `false`                                 | Opt into `<clan>.linker` (always runs with `image=true` or `audio=true`) |
| `linker_model`          | model | `@xlarge`                               | Model for `<clan>.linker`                                |
| `audio`                 | bool | `false`                                 | Opt into `<clan>.audio` (implies the linker)             |
| `audio_model`           | model | `@audio`                                | Model for `<clan>.audio`                                 |
| `audio_edition`         | `sase-research-artifacts@audio_edition` | `brief` | Narration edition for `<clan>.audio` (`brief` or `full`) |

Quote `wait` when passing several comma-separated agents (`wait="a,b"`); an unquoted
comma is parsed as a separate macro argument.

A three-agent macro swarm by default (codex + claude researchers plus the lead), up
to nine launched agents (five researchers, the lead, the image agent, the linker
agent, the audio agent). Each enabled researcher is rendered from one shared
researcher template. `grok=true` /
`muse=true` / `gemini=true` each add a researcher; `codex=false` (or any provider flag
`false`) drops one; turning all five off leaves exactly the lead running solo. A
provider that is hard-disabled drops its researcher even when its boolean input
is true; a soft-disabled provider still runs its researcher (soft disables never
refuse explicit model launches). When `image=true` or `audio=true` opts into those segments, the default set
runs five agents, because each implies the linker; both together run six.
Optional `wait` gates only the researchers. Optional `priority`
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
`#research_swarm(prompt="A research topic", audio=true)`, and `audio_edition`
(default `brief`), for example
`#research_swarm(prompt="A research topic", audio=true, audio_edition=full)`.
A fresh swarm podcast defaults to brief; supplying `audio_edition` alone never
launches the audio agent. Edition selection affects newly authored narration,
not whether audio is enabled.
The `muse-spark-1.3-contributor` default carries SASE's `warn` model advisory
("trains on your data"), which is part of why `muse` defaults off. The `agy`
provider rejects explicit `@effort` suffixes, so the `gemini_model` default carries
no effort suffix and effort is chosen via the model slug (`-high`/`-medium`/`-low`).

1. **`<clan>.cdx`** -- the codex researcher (`codex/gpt-6.1-sol@xhigh`), writing a
   self-named descriptive report via `#research(suffix=cdx)`; when supplied, also waits
   on the `wait` argument's agent(s). Rendered only when `codex` is true
   and the provider is not hard-disabled.
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
   `image=true` or `audio=true`. Waits on the lead (and on the image agent when
   `image=true`, and on the audio agent when `audio=true`) without forking, finds
   the lead's `<name>__final.md` through `wait.artifacts`, and writes and
   registers the canonical, well-structured `<name>.md`. The file opens with the
   title, then a short research-query summary of the swarm's `prompt`, then the
   listen card when audio succeeded, then the infographic when one was generated,
   then the `## Bottom line` / `## Overview` section. Restructured sections with
   checked links and in-document jump links follow.
9. **`<clan>.audio`** -- optional; when `audio=true`, waits only on the lead and
   never on the linker, running alongside the optional image agent, forks from
   the lead's segment, then runs `#research/audio(edition=<audio_edition>)`
   using `audio_model` (default `@audio`) and `audio_edition` (default `brief`;
   `brief` or `full` are the supported guide-backed authoring choices) with a
   generated podcast title card. `audio=true` implies the linker, which joins
   all enabled outputs and publishes a listen card. Requires
   `sase plugin install listen` (preferred) or `uv tool install sase-listen`.

The handoff contract: the lead writes `<name>__final.md` (instead of `<name>.md`) and
registers it only when the linker runs, and the linker derives its output directory
from that registered label rather than the current date. The linker is an editor, not
a researcher: it must not add claims or sources, and it leaves the lead's report as
written when it disagrees with it.

Execution matrix (default researchers cdx + cld):

| `audio` | `image` | `linker` arg | Agents | Lead writes  | Hook-eligible file                 |
| ------- | ------- | ------------ | ------ | ------------ | ---------------------------------- |
| false   | false   | false        | 3      | `<name>.md`  | lead's `<name>.md`                 |
| false   | false   | true         | 4      | `__final.md` | linker's `<name>.md`               |
| false   | true    | (implied)    | 5      | `__final.md` | linker's `<name>.md` + infographic |
| true    | false   | (implied)    | 5      | `__final.md` | linker's `<name>.md` + listen card |
| true    | true    | (implied)    | 6      | `__final.md` | both companions                    |

`image=true` or `audio=true` implies the linker: only the linker's `<name>.md` is
hook-eligible. The narration script is excluded from both the `@research`
inventory and the Highlights hook, like the infographic companion pages. No MP3
enters the public research repo.

### Listen card

When `audio=true` and the audio agent completes with `ok: true`, the linker
inserts a listen card directly below the research-query blockquote and above
the infographic (order: frontmatter, `#` title, research query, listen card,
infographic, bottom-line section):

```markdown
<div class="listen">

♫ **Brief audio edition** · 4 min · 3 chapters ·
[Narration script](<name>_narration.md)

</div>
```

and copies these numbers into report frontmatter (no library path, MP3 path,
feed URL, artifact id, or `file:` ref):

```yaml
audio:
  edition: brief
  duration_s: 250.34
  chapter_count: 3
  episode_id: a-listen-link-for-research-reports-d74298
```

Minutes are `max(1, round(duration_s / 60))`; the edition word is capitalized;
`1 chapter` is singular; the chapters segment is dropped when the count is
unknown; the narration-script link is included only when
`<name>_narration.md` exists beside the report.

A failed TTS render completes the audio agent with `audio.ok=false` and no
artifact, so the linker publishes without a card or `audio:` frontmatter and
says so (never "audio pending"). A *crashed* audio agent parks the linker
exactly like a crashed image agent: named waits release only on completion
(SASE posts a "Wait dependency can never self-resolve" notification). Rerun
the named `research.<N>.audio` agent or kill the parked linker.
`<name>__final.md` stays in the repo either way. If the image agent completes
without producing a PNG, the linker publishes without it and says so.

The audio agent's `sase var set audio` is keyed in the linker's `agents`
namespace by the producer's stable name: a clan member such as
`%id(audio, clan=research.{@1})` is `research.<n>.audio` (the concrete dotted
name), while a keyed template such as `%id:build-@` is the template base
(`build`, not `build-0`). The linker therefore iterates every `agents` entry
that carries an `audio` variable rather than hard-coding a key. A
`/sase_monitor` handoff inside the audio agent keeps `%wait:research.{@1}.audio`
unresolved until the follow-up turn settles (`resolve_wait_dependency` goes
through the clan/session container). The follow-up's `sase var set audio`
writes the same artifacts dir the linker later reads via
`resolve_resume_agent_name`. If the variable is missing, the linker falls
back to a `wait.artifacts` entry labeled `audio:<episode_id>` and
`sase listen ls <episode_id> --json` (or `sase-listen ls <episode_id> --json`,
or `uvx sase-listen ls <episode_id> --json`).

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
