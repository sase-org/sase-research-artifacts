---
description:
  Launch independent per-provider research agents, then have a lead researcher extend
  and consolidate their findings. Optionally critique the consolidated report and
  generate an infographic.
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
  - name: runners
    type: int
    default: null
    description:
      Optional positive-integer `%queue` capacity budget applied to every swarm member.
      If null, every segment authors the default `1.5x` multiplier (1.5 times this
      machine's effective `max_running_agents` budget). When supplied, it replaces
      the multiplier with an absolute budget.
  - name: codex
    type: bool
    default: true
    description: Request the codex researcher.
  - name: claude
    type: bool
    default: true
    description: Request the claude researcher.
  - name: grok
    type: bool
    default: false
    description: Request the grok researcher.
  - name: muse
    type: bool
    default: false
    description: Request the muse researcher.
  - name: gemini
    type: bool
    default: false
    description: Request the gemini (Antigravity) researcher.
  - name: codex_model
    type: word
    default: "codex/gpt-5.6-sol@xhigh"
    description: Model for `<clan>.cdx`.
  - name: claude_model
    type: word
    default: "claude/opus@xhigh"
    description: Model for `<clan>.cld`.
  - name: grok_model
    type: word
    default: "grok/grok-4.6@xhigh"
    description: Model for `<clan>.grk`.
  - name: muse_model
    type: word
    default: "muse/muse-spark-1.3-contributor@xhigh"
    description:
      Model for `<clan>.mus`. The default carries SASE's `warn` model advisory
      ("trains on your data"), which is part of why `muse` defaults off.
  - name: gemini_model
    type: word
    default: "agy/gemini-3.8-flash-high"
    description:
      Model for `<clan>.gem`. Antigravity (`agy`) rejects explicit `@effort`
      suffixes; choose effort through the model slug (`-high`/`-medium`/`-low`).
  - name: lead_model
    type: word
    default: "@xlarge"
    description:
      Model alias or provider model for the `.final` lead researcher and consolidator.
  - name: image
    type: bool
    default: false
    description: Generate an infographic after the lead researcher finishes.
  - name: critique
    type: bool
    default: false
    description:
      Run a critique agent after the lead researcher. It stress-tests and improves the
      consolidated report and writes `<name>__critique.md` beside it without modifying
      the lead's report.
  - name: critique_model
    type: word
    default: "@xlarge"
    description:
      Model alias or provider model for the optional `<clan>.critique` agent. Choosing a
      different provider than `lead_model` reduces shared blind spots.
---
{%- set researchers =
  ([{"short": "cdx", "provider": "codex", "model": codex_model}] if codex and ("codex" | provider_enabled("hard")) else [])
+ ([{"short": "cld", "provider": "claude", "model": claude_model}] if claude and ("claude" | provider_enabled("hard")) else [])
+ ([{"short": "grk", "provider": "grok", "model": grok_model}] if grok and ("grok" | provider_enabled("hard")) else [])
+ ([{"short": "mus", "provider": "muse", "model": muse_model}] if muse and ("muse" | provider_enabled("hard")) else [])
+ ([{"short": "gem", "provider": "agy", "model": gemini_model}] if gemini and ("agy" | provider_enabled("hard")) else [])
-%}
{%- set ns = namespace(layout_lines=["<month-dir>/<name>/"]) -%}
{%- for r in researchers -%}
{%- set _ = ns.layout_lines.append("├── <name>__" ~ r.short ~ ".md") -%}
{%- endfor -%}
{%- set _ = ns.layout_lines.append("└── <name>.md") -%}
{%- set layout_body = ns.layout_lines | join("\n") -%}
{%- set cns = namespace(critique_layout_lines=["<month-dir>/<name>/"]) -%}
{%- for r in researchers -%}
{%- set _ = cns.critique_layout_lines.append("├── <name>__" ~ r.short ~ ".md") -%}
{%- endfor -%}
{%- set _ = cns.critique_layout_lines.append("├── <name>.md") -%}
{%- set _ = cns.critique_layout_lines.append("└── <name>__critique.md") -%}
{%- set critique_layout_body = cns.critique_layout_lines | join("\n") -%}
%if(should_run={{ codex and ("codex" | provider_enabled("hard")) }}) %id(cdx, clan=research.{@1})
%m:{{ codex_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %})
{% set peers = researchers | rejectattr("short", "equalto", "cdx") | list %}
You are researcher cdx in a {{ researchers | length }}-researcher swarm.
{% if peers -%}
The other {{ "researcher" if peers | length == 1 else "researchers" }}, {% for p in peers %}`research.{@1}.{{ p.short }}`{% if not loop.last %}, {% endif %}{% endfor %}, {{ "is" if peers | length == 1 else "are" }} independently investigating the same request and will write {{ "its" if peers | length == 1 else "their" }} own self-named {{ "report" if peers | length == 1 else "reports" }} ending in {% for p in peers %}`__{{ p.short }}.md`{% if not loop.last %} and {% endif %}{% endfor %}. Your report will end in `__cdx.md`.
{% else -%}
You are the only independent researcher in this swarm. Your report will end in `__cdx.md`.
{% endif %}
Conduct your research independently and form your own conclusions. Do NOT attempt to
locate, open, read, or otherwise consult the other researcher's report from this swarm,
even if it becomes available before you finish. Do not obtain that peer's findings
indirectly through its chat transcript, summaries, or requests to the peer. You may
independently use the same external sources, shared input material, and unrelated prior
research. You may check filenames or file existence to avoid overwriting your own
output, but do not inspect the peer's report contents. If you encounter its filename,
leave the report alone. The lead researcher will read every report and synthesize their
findings after you have all finished.

{{ prompt }} #research(suffix=cdx)

---

%if(should_run={{ claude and ("claude" | provider_enabled("hard")) }}) %id(cld, clan=research.{@1})
%m:{{ claude_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %})
{% set peers = researchers | rejectattr("short", "equalto", "cld") | list %}
You are researcher cld in a {{ researchers | length }}-researcher swarm.
{% if peers -%}
The other {{ "researcher" if peers | length == 1 else "researchers" }}, {% for p in peers %}`research.{@1}.{{ p.short }}`{% if not loop.last %}, {% endif %}{% endfor %}, {{ "is" if peers | length == 1 else "are" }} independently investigating the same request and will write {{ "its" if peers | length == 1 else "their" }} own self-named {{ "report" if peers | length == 1 else "reports" }} ending in {% for p in peers %}`__{{ p.short }}.md`{% if not loop.last %} and {% endif %}{% endfor %}. Your report will end in `__cld.md`.
{% else -%}
You are the only independent researcher in this swarm. Your report will end in `__cld.md`.
{% endif %}
Conduct your research independently and form your own conclusions. Do NOT attempt to
locate, open, read, or otherwise consult the other researcher's report from this swarm,
even if it becomes available before you finish. Do not obtain that peer's findings
indirectly through its chat transcript, summaries, or requests to the peer. You may
independently use the same external sources, shared input material, and unrelated prior
research. You may check filenames or file existence to avoid overwriting your own
output, but do not inspect the peer's report contents. If you encounter its filename,
leave the report alone. The lead researcher will read every report and synthesize their
findings after you have all finished.

{{ prompt }} #research(suffix=cld)

---

%if(should_run={{ grok and ("grok" | provider_enabled("hard")) }}) %id(grk, clan=research.{@1})
%m:{{ grok_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %})
{% set peers = researchers | rejectattr("short", "equalto", "grk") | list %}
You are researcher grk in a {{ researchers | length }}-researcher swarm.
{% if peers -%}
The other {{ "researcher" if peers | length == 1 else "researchers" }}, {% for p in peers %}`research.{@1}.{{ p.short }}`{% if not loop.last %}, {% endif %}{% endfor %}, {{ "is" if peers | length == 1 else "are" }} independently investigating the same request and will write {{ "its" if peers | length == 1 else "their" }} own self-named {{ "report" if peers | length == 1 else "reports" }} ending in {% for p in peers %}`__{{ p.short }}.md`{% if not loop.last %} and {% endif %}{% endfor %}. Your report will end in `__grk.md`.
{% else -%}
You are the only independent researcher in this swarm. Your report will end in `__grk.md`.
{% endif %}
Conduct your research independently and form your own conclusions. Do NOT attempt to
locate, open, read, or otherwise consult the other researcher's report from this swarm,
even if it becomes available before you finish. Do not obtain that peer's findings
indirectly through its chat transcript, summaries, or requests to the peer. You may
independently use the same external sources, shared input material, and unrelated prior
research. You may check filenames or file existence to avoid overwriting your own
output, but do not inspect the peer's report contents. If you encounter its filename,
leave the report alone. The lead researcher will read every report and synthesize their
findings after you have all finished.

{{ prompt }} #research(suffix=grk)

---

%if(should_run={{ muse and ("muse" | provider_enabled("hard")) }}) %id(mus, clan=research.{@1})
%m:{{ muse_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %})
{% set peers = researchers | rejectattr("short", "equalto", "mus") | list %}
You are researcher mus in a {{ researchers | length }}-researcher swarm.
{% if peers -%}
The other {{ "researcher" if peers | length == 1 else "researchers" }}, {% for p in peers %}`research.{@1}.{{ p.short }}`{% if not loop.last %}, {% endif %}{% endfor %}, {{ "is" if peers | length == 1 else "are" }} independently investigating the same request and will write {{ "its" if peers | length == 1 else "their" }} own self-named {{ "report" if peers | length == 1 else "reports" }} ending in {% for p in peers %}`__{{ p.short }}.md`{% if not loop.last %} and {% endif %}{% endfor %}. Your report will end in `__mus.md`.
{% else -%}
You are the only independent researcher in this swarm. Your report will end in `__mus.md`.
{% endif %}
Conduct your research independently and form your own conclusions. Do NOT attempt to
locate, open, read, or otherwise consult the other researcher's report from this swarm,
even if it becomes available before you finish. Do not obtain that peer's findings
indirectly through its chat transcript, summaries, or requests to the peer. You may
independently use the same external sources, shared input material, and unrelated prior
research. You may check filenames or file existence to avoid overwriting your own
output, but do not inspect the peer's report contents. If you encounter its filename,
leave the report alone. The lead researcher will read every report and synthesize their
findings after you have all finished.

{{ prompt }} #research(suffix=mus)

---

%if(should_run={{ gemini and ("agy" | provider_enabled("hard")) }}) %id(gem, clan=research.{@1})
%m:{{ gemini_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %})
{% set peers = researchers | rejectattr("short", "equalto", "gem") | list %}
You are researcher gem in a {{ researchers | length }}-researcher swarm.
{% if peers -%}
The other {{ "researcher" if peers | length == 1 else "researchers" }}, {% for p in peers %}`research.{@1}.{{ p.short }}`{% if not loop.last %}, {% endif %}{% endfor %}, {{ "is" if peers | length == 1 else "are" }} independently investigating the same request and will write {{ "its" if peers | length == 1 else "their" }} own self-named {{ "report" if peers | length == 1 else "reports" }} ending in {% for p in peers %}`__{{ p.short }}.md`{% if not loop.last %} and {% endif %}{% endfor %}. Your report will end in `__gem.md`.
{% else -%}
You are the only independent researcher in this swarm. Your report will end in `__gem.md`.
{% endif %}
Conduct your research independently and form your own conclusions. Do NOT attempt to
locate, open, read, or otherwise consult the other researcher's report from this swarm,
even if it becomes available before you finish. Do not obtain that peer's findings
indirectly through its chat transcript, summaries, or requests to the peer. You may
independently use the same external sources, shared input material, and unrelated prior
research. You may check filenames or file existence to avoid overwriting your own
output, but do not inspect the peer's report contents. If you encounter its filename,
leave the report alone. The lead researcher will read every report and synthesize their
findings after you have all finished.

{{ prompt }} #research(suffix=gem)

---

%clan(research.{@1}, tribe=research, summary=[[[bold]RESEARCH PROMPT:[/bold] {{ prompt }}]]) %id:research.{@1}.final %m:{{ lead_model }}
{% for r in researchers %}%wait:research.{@1}.{{ r.short }} {% endfor %}%q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %})

{% if researchers -%}
You are the lead researcher: {{ researchers | length }} independent {{ "researcher has" if researchers | length == 1 else "researchers have" }} reported on the request
below, and you will add your own research and merge every perspective into one
consolidated report.
{% else -%}
You are the lead researcher: no independent researchers ran for this dispatch, so you
are running as a solo researcher on the request below.
{% endif %}
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

{% if researchers -%}
1. From the registered reports above, identify exactly one report per expected suffix
   in {{ researchers | map(attribute='short') | join(', ') }}, belonging to this
   dispatch's {% for r in researchers %}`research.{@1}.{{ r.short }}`{% if not loop.last %}, {% endif %}{% endfor %} {{ "dependency" if researchers | length == 1 else "dependencies" }}, matching by `wait_name` and the canonical research
   label's existing `__<suffix>.md` suffix. Never reassign suffixes from list order.
   Open the research repo with `/sase_repo`, then read each report through its canonical
   research reference (or the `ref` field's `file:<id>` reference if the original has
   moved) using `sase artifact read`. Do not read predecessor chat transcripts. If the
   records above do not identify exactly one report per expected suffix, stop and report
   the missing or ambiguous input instead of guessing.
2. Research the request yourself, prioritizing gaps, weak evidence, and disagreements
   between the reports.
3. Pick a descriptive stem `<name>` that collides with nothing in the month directory
   (do NOT end the name with `_consolidated` or `_<YYYYmmdd>` or anything similar unless
   it relates to the research topic), create `<month-dir>/<name>/`, and move each report
   inside it as `<name>__<suffix>.md`, preserving its existing suffix. Each report's
   `source_path` is provenance for where it lives in your own opened research checkout;
   resolve its canonical repo-relative path there before moving it. Never modify the
   other agents' checkouts or the stored snapshot recorded at `ref` — only the copy in
   your own checkout moves. Preserve every file and never overwrite: on any collision,
   pick a different stem first.
4. Write the consolidated report to `<name>/<name>.md`: merge the strongest findings
   from every report above and your own research, resolve conflicts, cut duplication,
   and add missing critical context without unnecessary length.
{%- if critique %}

5. After the write succeeds, register the consolidated report as a durable snapshot so
   the critique agent, `research.{@1}.critique`, can find it:

   sase artifact create -p "<absolute-report-path>" -l "research:<repo-relative-report-path>"

   Use the consolidated report's actual absolute path and its path relative to the
   research repo root, for example `research:202609/<name>/<name>.md`. Register only the
   consolidated report, and do not pass `--move`. If registration fails, report that
   failure; do not report the task as fully complete.
{%- endif %}

Final layout:

{{ "```text\n" ~ layout_body ~ "\n```" }}
{% else -%}
1. No independent researcher reports are expected for this dispatch; skip report
   identification and proceed as the sole researcher.
2. Research the request yourself.
3. Pick a descriptive stem `<name>` that collides with nothing in the month directory
   (do NOT end the name with `_consolidated` or `_<YYYYmmdd>` or anything similar unless
   it relates to the research topic), create `<month-dir>/<name>/`, and write your
   report there with no researcher reports to move.
4. Write the consolidated report to `<name>/<name>.md` based on your own research,
   adding missing critical context without unnecessary length.
{%- if critique %}

5. After the write succeeds, register the consolidated report as a durable snapshot so
   the critique agent, `research.{@1}.critique`, can find it:

   sase artifact create -p "<absolute-report-path>" -l "research:<repo-relative-report-path>"

   Use the consolidated report's actual absolute path and its path relative to the
   research repo root, for example `research:202609/<name>/<name>.md`. Register only the
   consolidated report, and do not pass `--move`. If registration fails, report that
   failure; do not report the task as fully complete.
{%- endif %}

Final layout:

```text
<month-dir>/<name>/
└── <name>.md
```
{% endif %}
---

%if(should_run={{ image }}) %id(image, clan=research.{@1}) %model:@image
%wait:research.{@1}.final %q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %}) #fork:research.{@1}.final #research/image
---

%if(should_run={{ critique }}) %id(critique, clan=research.{@1}) %m:{{ critique_model }}
%wait:research.{@1}.final %q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %})

You are the critique agent for a research swarm. The lead researcher,
`research.{@1}.final`, has written a consolidated report on the request below. Your job
is to stress-test that report and improve on it in a new companion report. People
deciding what to believe, and agents implementing a solution, will read the lead's report
and yours side by side, so yours must make the pair more trustworthy and more actionable
than the lead's report alone. Critique without improvement is half the job: wherever you
find a problem, do the research needed to fix it.

SASE derives your plan's links from the artifacts you read this turn; use
`sase artifact read` for context you actually used.

Research request:

{{ prompt }}

The lead researcher's registered reports:

{% raw %}{% for a in wait.artifacts if a.kind == "markdown" and a.label and a.label.startswith("research:") %}
- wait_name={{ a.wait_name }} label={{ a.label }} source_path={{ a.source_path }} path={{ a.path }} ref={{ a.ref }}
{% endfor %}{% endraw %}

Steps:

1. Before you read the lead's report, list for yourself the questions a complete answer
   to the request must settle and the evidence that would settle each. Use that list as
   your checklist so the report's framing does not quietly become yours.
2. From the registered reports above, identify the lead's consolidated report: exactly
   one entry with `wait_name` `research.{@1}.final` whose label has the form
   `research:<YYYYMM>/<name>/<name>.md` (its filename stem equals its parent directory
   name and carries no `__<suffix>`). Ignore every other entry. If there is not exactly
   one such entry, stop and report the missing or ambiguous input instead of guessing.
   Open the research repo with `/sase_repo`, then read the report through its canonical
   research reference (or the `ref` field's `file:<id>` reference if the original has
   moved) using `sase artifact read`. Do not read the lead's or any researcher's chat
   transcript. Never modify, move, or rename the lead's report or any researcher draft.
{% if researchers -%}
3. The lead consolidated {{ researchers | length }} independent researcher {{ "draft" if researchers | length == 1 else "drafts" }}, which now {{ "sits" if researchers | length == 1 else "sit" }} beside its report as {% for r in researchers %}`<name>__{{ r.short }}.md`{% if not loop.last %}, {% endif %}{% endfor %}.
   After forming your own view of the lead's report, read each draft with
   `sase artifact read` through its `research:<YYYYMM>/<name>/<name>__<suffix>.md`
   reference to check synthesis fidelity: findings or caveats the lead dropped,
   disagreements it settled without evidence, and consensus it overstated. Treat the
   drafts as evidence to weigh, not as authorities. A missing draft is worth noting but is
   not a reason to stop.
{% else -%}
3. No independent researchers ran for this dispatch, so the lead's report is a single
   researcher's work with no drafts to cross-check. That makes independent verification
   in the next steps more important.
{% endif -%}
4. Review the lead's report against your checklist, most important questions first:
   - Does it answer the request that was actually asked, including its implicit
     constraints, rather than a neighboring, easier question?
   - Do the load-bearing claims (the ones its conclusions or recommendation depend on)
     hold up? Verify each against primary sources such as official documentation,
     specifications, source code, papers, or data. Check that every cited source says
     what the report says it does, and flag stale versions, numbers, and dates.
   - Is the reasoning sound? Look for unsupported leaps, overgeneralization, false
     dichotomies, cherry-picked evidence, and correlation read as causation.
   - What is the strongest case against its recommendation? Steelman the best
     alternative and decide whether it should win.
   - What is missing: credible alternatives or prior art, costs, risks and failure
     modes, constraints, edge cases, and migration or rollback concerns?
   - Could someone act on it? Check that the recommendation is specific, gives decision
     criteria, states confidence that matches the evidence, and names its open questions.
5. Improve on what you find. Research each significant problem until you can confirm or
   correct it, fill each important gap, and evaluate any alternative the report missed.
   Where you cannot settle something, say exactly which evidence, experiment, or decision
   would settle it. Say which of your own claims you verified against a primary source,
   which you inferred, and how confident you are. Record the load-bearing claims you
   checked and found sound: knowing what to trust is as useful as knowing what not to.
   Do not manufacture criticism or pad with style nitpicks. If the report holds up, say
   so plainly and keep your report short.
6. Write your report to `<name>__critique.md` in the lead report's directory, that is
   `<YYYYMM>/<name>/<name>__critique.md`, taking `<YYYYMM>/<name>/` from the lead
   report's label, never from the current date. Create it without overwrite: if the file
   already exists, stop and report the collision visibly instead of replacing it or
   choosing another name. Follow the research repo's `README.md` conventions when
   present, and mirror the lead report's frontmatter conventions (such as `create_time`,
   `updated_time`, `status`, and `tags`) when it has them. Use this structure, omitting a
   section only when it would be empty:
   - A title naming the lead report's topic, and a relative link to `<name>.md` near the
     top.
   - Verdict: two to five sentences saying whether the lead's main conclusion holds
     (holds, holds with corrections, or does not hold), how far the report can be
     trusted, and the single most important correction.
   - Revised bottom line: the corrected, self-contained answer or recommendation a
     reader or implementer should act on, stating what stands and what changes from the
     lead's report.
   - Findings, ordered by severity: critical (changes the conclusion or
     recommendation), major (materially affects a decision or an implementation), then
     minor (worth fixing). For each, give where it occurs in the lead's report (section
     heading), the problem, the evidence with sources, the fix, and its effect on the
     conclusion.
   - Verified claims: the load-bearing claims you checked and confirmed, with sources.
{% if researchers %}   - Synthesis check: researcher findings the lead dropped or misrepresented, and
     disagreements it left unresolved.
{% endif %}   - Open questions: what neither report settles, and what would settle each.

   Reference the lead's report by section instead of restating it: yours is a companion,
   not a rewrite. Even so, a reader must be able to act on your verdict and revised
   bottom line without opening anything else.
7. After the write succeeds, register your report as a durable snapshot:

   sase artifact create -p "<absolute-report-path>" -l "research:<repo-relative-report-path>"

   Use the report's actual absolute path and its path relative to the research repo
   root, for example `research:202609/<name>/<name>__critique.md`. Do not pass `--move`.
   If registration fails, report that failure; do not report the task as fully complete.

Final layout:

{{ "```text\n" ~ critique_layout_body ~ "\n```" }}
