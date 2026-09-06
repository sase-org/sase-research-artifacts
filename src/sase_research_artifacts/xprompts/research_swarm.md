---
description:
  Launch two independent research agents, then have a lead researcher extend and
  consolidate their findings and generate an infographic.
input:
  - name: prompt
    type: text
    description: Research topic or question for the swarm to investigate.
  - name: wait
    type: word
    default: null
    description:
      Name of the sase agent to wait for before starting the swarm. Quote the value to
      pass several comma-separated agents (`wait="a,b"`); an unquoted comma is parsed as
      a separate xprompt argument. If null, the swarm starts immediately.
  - name: priority
    type: int
    default: null
    description:
      Optional runner-queue priority applied to every swarm member. Lower numbers start
      first. If null, the swarm uses SASE's implicit queue priority.
---

%clan(research.{@1}, tribe=research,
summary=[[[bold]RESEARCH PROMPT:[/bold] {{ prompt }}]]) %id:research.{@1}.cdx
%model:@research_a {% if wait %}
%wait:{{ wait }} {% endif %}{% if priority is not none %}
%wait(priority={{ priority }}) {% endif %}
You are researcher A in a two-researcher swarm. The other researcher,
`research.{@1}.cld`, is independently investigating the same request and will write its
own self-named report ending in `__b.md`. Your report will end in `__a.md`.

Conduct your research independently and form your own conclusions. Do NOT attempt to
locate, open, read, or otherwise consult the other researcher's report from this swarm,
even if it becomes available before you finish. Do not obtain that peer's findings
indirectly through its chat transcript, summaries, or requests to the peer. You may
independently use the same external sources, shared input material, and unrelated prior
research. You may check filenames or file existence to avoid overwriting your own
output, but do not inspect the peer's report contents. If you encounter its filename,
leave the report alone. The lead researcher will read both reports and synthesize their
findings after you have both finished.

{{ prompt }} #research(suffix=a)

---

%id(cld, clan=research.{@1}) %m:@research_b {% if wait %}
%wait:{{ wait }} {% endif %}{% if priority is not none %}
%wait(priority={{ priority }}) {% endif %}
You are researcher B in a two-researcher swarm. The other researcher,
`research.{@1}.cdx`, is independently investigating the same request and will write its
own self-named report ending in `__a.md`. Your report will end in `__b.md`.

Conduct your research independently and form your own conclusions. Do NOT attempt to
locate, open, read, or otherwise consult the other researcher's report from this swarm,
even if it becomes available before you finish. Do not obtain that peer's findings
indirectly through its chat transcript, summaries, or requests to the peer. You may
independently use the same external sources, shared input material, and unrelated prior
research. You may check filenames or file existence to avoid overwriting your own
output, but do not inspect the peer's report contents. If you encounter its filename,
leave the report alone. The lead researcher will read both reports and synthesize their
findings after you have both finished.

{{ prompt }} #research(suffix=b)

---

%id(final, clan=research.{@1}) %m:@xlarge
%wait:research.{@1}.cdx %wait:research.{@1}.cld {% if priority is not none %}
%wait(priority={{ priority }}) {% endif %}

You are the lead researcher: two independent researchers have reported on the request
below, and you will add your own research and merge all three perspectives into one
consolidated report.

SASE derives your plan's links from the artifacts you read this turn; use
`sase artifact read` for context you actually used.

Research request:

{{ prompt }}

The researchers' registered reports:

{% raw %}{% for a in wait.artifacts if a.kind == "markdown" and a.label and a.label.startswith("research:") %}
- wait_name={{ a.wait_name }} label={{ a.label }} source_path={{ a.source_path }} path={{ a.path }} ref={{ a.ref }}
{% endfor %}{% endraw %}

Month directory (create it if missing):

$(sase repo path research --ensure)/$(date +%Y%m)

Steps:

1. From the registered reports above, identify the one distinct A report and the one
   distinct B report belonging to this dispatch's `research.{@1}.cdx` and
   `research.{@1}.cld` dependencies, matching by `wait_name` and the canonical research
   label's existing `__a.md`/`__b.md` suffix. Never reassign `__a`/`__b` from list order.
   Open the research repo with `/sase_repo`, then read each report through its canonical
   research reference (or the `ref` field's `file:<id>` reference if the original has
   moved) using `sase artifact read`. Do not read predecessor chat transcripts. If the
   records above do not identify exactly one A report and one B report, stop and report
   the missing or ambiguous input instead of guessing.
2. Research the request yourself, prioritizing gaps, weak evidence, and disagreements
   between the two reports.
3. Pick a descriptive stem `<name>` that collides with nothing in the month directory
   (do NOT end the name with `_consolidated` or `_<YYYYmmdd>` or anything similar unless
   it relates to the research topic), create `<month-dir>/<name>/`, and move the two
   reports inside it as `<name>__a.md` and `<name>__b.md`, preserving each report's
   existing `__a`/`__b` suffix. Each report's `source_path` is provenance for where it
   lives in your own opened research checkout; resolve its canonical repo-relative path
   there before moving it. Never modify the other agents' checkouts or the stored
   snapshot recorded at `ref` — only the copy in your own checkout moves. Preserve both
   files and never overwrite: on any collision, pick a different stem first.
4. Write the consolidated report to `<name>/<name>.md`: merge the strongest findings
   from both reports and your own research, resolve conflicts, cut duplication, and add
   missing critical context without unnecessary length.

Final layout:

```text
<month-dir>/<name>/
├── <name>__a.md
├── <name>__b.md
└── <name>.md
```

---

%id(image, clan=research.{@1}) %model:@image
%wait:research.{@1}.final {% if priority is not none %}
%wait(priority={{ priority }}) {% endif %}#fork:research.{@1}.final #research/image
