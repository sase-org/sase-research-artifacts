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

## `#research_swarm` -- Two Researchers Plus a Lead

### Input

| Name       | Type | Description                                                        |
| ---------- | ---- | ------------------------------------------------------------------ |
| `prompt`   | text | Research topic or question for the swarm to investigate            |
| `wait`     | word | Optional agent(s) to wait for before the swarm starts              |
| `priority` | int  | Optional integer queue priority for all four agents; no default    |

Quote `wait` when passing several comma-separated agents (`wait="a,b"`); an unquoted
comma is parsed as a separate xprompt argument.

A four-segment xprompt swarm. Optional `wait` gates only `cdx`/`cld`. Optional
`priority` applies to all four agents when supplied (lower values start first);
omission uses SASE's implicit queue priority.

1. **`<clan>.cdx`** -- the primary researcher (`@research_a`), tagged with the
   `research` tribe, writing a self-named descriptive report via `#research(suffix=a)`;
   when supplied, also waits on the `wait` argument's agent(s).
2. **`<clan>.cld`** -- the second-opinion researcher (`@research_b`), run independently
   in parallel, writing a self-named descriptive report via `#research(suffix=b)`; when
   supplied, also waits on the `wait` argument's agent(s).
3. **`<clan>.final`** -- the lead researcher (`@xlarge`), waiting on both prior
   segments, who reads both registered reports, does further research, and writes a
   consolidated report merging all three perspectives. Individual researcher reports
   move to `<name>__a.md` / `<name>__b.md` under `<name>/`, preserving each report's
   existing suffix; the consolidated report is `<name>/<name>.md`.
4. **`<clan>.image`** -- waits on and forks from the lead's segment, then runs
   `#research/image` against the consolidated report using `@image`.

Each of `cdx` and `cld` is told the other researcher's agent ID and the `__a`/`__b`
suffix its report filename will end with, and is explicitly instructed not to seek out
or read that peer's report, or its findings indirectly via the peer's chat transcript,
for the duration of the current swarm. Combining the two reports remains the lead's
responsibility.

The lead's prompt no longer reads its predecessors' chat transcripts to discover their
report paths. Instead it renders a raw-protected loop over sase's runtime `wait`
namespace, `wait.artifacts`, which is populated lazily (with one batched query) only
when the lead's prompt actually renders and only lists non-chat artifacts registered by
`cdx`/`cld`. The loop filters to markdown entries whose label carries the canonical
`research:<repo-relative-path>` report reference from `#research`'s registration step,
and prints each entry's `wait_name`, `label`, `source_path`, `path`, and durable `ref`.
The lead matches the `.cdx`/`.cld` `wait_name` to the `__a`/`__b` suffix already on the
label, never by list order, then reads each report through its canonical research
reference (or the `ref` fallback) with `sase artifact read`.

Depends on the `research_a` / `research_b` / `image` model aliases and the
`researchers` bucket from this plugin's default config, plus SASE's built-in `@xlarge`
alias for the lead segment.
