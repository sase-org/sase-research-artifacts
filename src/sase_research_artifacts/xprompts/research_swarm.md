---
description:
  Launch independent per-provider research agents, then have a lead researcher extend
  and consolidate their findings. Optionally generate an infographic.
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
      If null, the swarm uses SASE's global runner-capacity budget.
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
  - name: lead_model
    type: word
    default: "@xlarge"
    description:
      Model alias or provider model for the `.final` lead researcher and consolidator.
  - name: should_generate_image
    type: bool
    default: false
    description: Generate an infographic after the lead researcher finishes.
---
{%- set researchers =
  ([{"short": "cdx", "provider": "codex", "model": codex_model}] if codex and ("codex" | provider_enabled) else [])
+ ([{"short": "cld", "provider": "claude", "model": claude_model}] if claude and ("claude" | provider_enabled) else [])
+ ([{"short": "grk", "provider": "grok", "model": grok_model}] if grok and ("grok" | provider_enabled) else [])
+ ([{"short": "mus", "provider": "muse", "model": muse_model}] if muse and ("muse" | provider_enabled) else [])
-%}
{%- set ns = namespace(layout_lines=["<month-dir>/<name>/"]) -%}
{%- for r in researchers -%}
{%- set _ = ns.layout_lines.append("├── <name>__" ~ r.short ~ ".md") -%}
{%- endfor -%}
{%- set _ = ns.layout_lines.append("└── <name>.md") -%}
{%- set layout_body = ns.layout_lines | join("\n") -%}
%if(should_run={{ codex and ("codex" | provider_enabled) }}) %id(cdx, clan=research.{@1})
%m:{{ codex_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q(w=0.25{% if runners is not none %}, capacity={{ runners }}{% endif %}{% if priority is not none %}, priority={{ priority }}{% endif %})
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

%if(should_run={{ claude and ("claude" | provider_enabled) }}) %id(cld, clan=research.{@1})
%m:{{ claude_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q(w=0.25{% if runners is not none %}, capacity={{ runners }}{% endif %}{% if priority is not none %}, priority={{ priority }}{% endif %})
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

%if(should_run={{ grok and ("grok" | provider_enabled) }}) %id(grk, clan=research.{@1})
%m:{{ grok_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q(w=0.25{% if runners is not none %}, capacity={{ runners }}{% endif %}{% if priority is not none %}, priority={{ priority }}{% endif %})
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

%if(should_run={{ muse and ("muse" | provider_enabled) }}) %id(mus, clan=research.{@1})
%m:{{ muse_model }} {% if wait %}%wait:{{ wait }} {% endif %}%q(w=0.25{% if runners is not none %}, capacity={{ runners }}{% endif %}{% if priority is not none %}, priority={{ priority }}{% endif %})
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

%clan(research.{@1}, tribe=research, summary=[[[bold]RESEARCH PROMPT:[/bold] {{ prompt }}]]) %id:research.{@1}.final %m:{{ lead_model }}
{% for r in researchers %}%wait:research.{@1}.{{ r.short }} {% endfor %}%q(w=0.25{% if runners is not none %}, capacity={{ runners }}{% endif %}{% if priority is not none %}, priority={{ priority }}{% endif %})

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

Final layout:

```text
<month-dir>/<name>/
└── <name>.md
```
{% endif %}
---

%if(should_run={{ should_generate_image }}) %id(image, clan=research.{@1}) %model:@image
%wait:research.{@1}.final %q(w=0.25{% if runners is not none %}, capacity={{ runners }}{% endif %}{% if priority is not none %}, priority={{ priority }}{% endif %}) #fork:research.{@1}.final #research/image
