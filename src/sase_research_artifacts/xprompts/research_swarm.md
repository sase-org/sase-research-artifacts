---
description:
  Launch independent per-provider research agents, then have a lead researcher extend
  and consolidate their findings. Optionally generate an infographic and/or a narrated
  audio edition; `image=true` or `audio=true` implies a linker agent that publishes
  the canonical report (with a listen card when audio succeeds).
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
      a separate macro argument. If null, the swarm starts immediately.
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
    type: model
    default: "codex/gpt-6.1-sol@xhigh"
    description: Model for `<clan>.cdx`.
  - name: claude_model
    type: model
    default: "claude/opus@xhigh"
    description: Model for `<clan>.cld`.
  - name: grok_model
    type: model
    default: "grok/grok-4.6@xhigh"
    description: Model for `<clan>.grk`.
  - name: muse_model
    type: model
    default: "muse/muse-spark-1.3-contributor@xhigh"
    description:
      Model for `<clan>.mus`. The default carries SASE's `warn` model advisory
      ("trains on your data"), which is part of why `muse` defaults off.
  - name: gemini_model
    type: model
    default: "agy/gemini-3.8-flash-high"
    description:
      Model for `<clan>.gem`. Antigravity (`agy`) rejects explicit `@effort`
      suffixes; choose effort through the model slug (`-high`/`-medium`/`-low`).
  - name: lead_model
    type: model
    default: "@xlarge"
    description:
      Model alias or provider model for the `.final` lead researcher and consolidator.
  - name: image
    type: bool
    default: false
    description:
      Generate an infographic after the lead researcher finishes. Implies the linker
      agent, which embeds the infographic directly above the published report's
      bottom line.
  - name: image_model
    type: model
    default: "@image"
    description: Model alias or provider model for the `<clan>.image` agent.
  - name: linker
    type: bool
    default: false
    description:
      Run a linker agent after the lead researcher (and after the image agent when
      `image=true`, and after the audio agent when `audio=true`). The lead then
      writes `<name>__final.md` while the linker publishes `<name>.md`. The linker
      always runs when `image=true` or `audio=true`.
  - name: linker_model
    type: model
    default: "@xlarge"
    description: Model alias or provider model for the `<clan>.linker` agent.
  - name: audio
    type: bool
    default: false
    description:
      Narrate the lead's consolidated report after the lead finishes, running
      alongside the optional image agent when `image=true` and using a generated
      title card. Implies the linker, which waits on this agent and publishes a
      listen card plus `audio:` frontmatter. A failed TTS render completes this
      agent with `audio.ok=false` so the linker publishes without a card.
  - name: audio_model
    type: model
    default: "@audio"
    description: Model alias or provider model for the `<clan>.audio` agent.
  - name: audio_edition
    type: sase-research-artifacts@audio_edition
    default: "brief"
    description:
      Narration edition passed to `#research/audio` when `audio=true` (`brief`
      runs about 4 minutes, `full` about 16 minutes). Supplying it alone never
      launches the audio agent and never implies the linker.
macros:
  _queue:
    description: Runner-queue admission shared by every swarm member.
    content: |-
      %q({% if runners is not none %}{{ runners }}{% else %}1.5x{% endif %}, w=0.25{% if priority is not none %}, priority={{ priority }}{% endif %})
  _report_records:
    description:
      Launch-time list of the research reports registered by the awaited agents.
    content: |-
      {% raw %}{% for a in wait.artifacts if a.kind == "markdown" and a.label and a.label.startswith("research:") %}
      - wait_name={{ a.wait_name }} label={{ a.label }} source_path={{ a.source_path }} path={{ a.path }} ref={{ a.ref }}
      {% endfor %}{% endraw %}
---
{%- set researchers =
  ([{"short": "cdx", "provider": "codex", "model": codex_model}] if codex and ("codex" | provider_enabled("hard")) else [])
+ ([{"short": "cld", "provider": "claude", "model": claude_model}] if claude and ("claude" | provider_enabled("hard")) else [])
+ ([{"short": "grk", "provider": "grok", "model": grok_model}] if grok and ("grok" | provider_enabled("hard")) else [])
+ ([{"short": "mus", "provider": "muse", "model": muse_model}] if muse and ("muse" | provider_enabled("hard")) else [])
+ ([{"short": "gem", "provider": "agy", "model": gemini_model}] if gemini and ("agy" | provider_enabled("hard")) else [])
-%}
{%- set run_linker = linker or image or audio -%}
{%- set lead_report = "<name>__final.md" if run_linker else "<name>.md" -%}
{%- set drafts = [] -%}
{%- for r in researchers %}{% set _ = drafts.append("<name>__" ~ r.short ~ ".md") %}{% endfor -%}
{%- set narration = ["<name>_narration.md"] if audio else [] -%}
{%- set lead_files = drafts + [lead_report] + narration -%}
{%- set linker_files = drafts + ["<name>__final.md"] + (["<name>_infographic.png"] if image else []) + ["<name>.md"] + narration -%}
{%- macro tree(files) -%}
{{ "```text" }}
<month-dir>/<name>/
{%- for f in files %}
{{ "└──" if loop.last else "├──" }} {{ f }}
{%- endfor %}
{{ "```" }}
{%- endmacro -%}
{%- for r in researchers %}
{%- set peers = researchers | rejectattr("short", "equalto", r.short) | list %}
%id({{ r.short }}, clan=research.{@1})
%m:{{ r.model }} {% if wait %}%wait:{{ wait }} {% endif %}#_queue

You are researcher {{ r.short }} in a {{ researchers | length }}-researcher swarm.
{% if peers -%}
The other {{ "researcher" if peers | length == 1 else "researchers" }}, {% for p in peers %}`research.{@1}.{{ p.short }}`{% if not loop.last %}, {% endif %}{% endfor %}, {{ "is" if peers | length == 1 else "are" }} independently investigating the same request and will write {{ "its" if peers | length == 1 else "their" }} own self-named {{ "report" if peers | length == 1 else "reports" }} ending in {% for p in peers %}`__{{ p.short }}.md`{% if not loop.last %} and {% endif %}{% endfor %}. Your report will end in `__{{ r.short }}.md`.
{% else -%}
You are the only independent researcher in this swarm. Your report will end in `__{{ r.short }}.md`.
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

{{ prompt }} #research(suffix={{ r.short }})

---
{% endfor %}

%clan(research.{@1}, tribe=research, summary=[[[bold]RESEARCH PROMPT:[/bold] {{ prompt }}]]) %id:research.{@1}.final %m:{{ lead_model }}
{% for r in researchers %}%wait:research.{@1}.{{ r.short }} {% endfor %}#_queue

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

#_report_records

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
4. Write the consolidated report to `<name>/{{ lead_report }}`: merge the strongest findings
   from every report above and your own research, resolve conflicts, cut duplication,
   and add missing critical context without unnecessary length.
{%- else -%}
1. No independent researcher reports are expected for this dispatch; skip report
   identification and proceed as the sole researcher.
2. Research the request yourself.
3. Pick a descriptive stem `<name>` that collides with nothing in the month directory
   (do NOT end the name with `_consolidated` or `_<YYYYmmdd>` or anything similar unless
   it relates to the research topic), create `<month-dir>/<name>/`, and write your
   report there with no researcher reports to move.
4. Write the consolidated report to `<name>/{{ lead_report }}` based on your own research,
   adding missing critical context without unnecessary length.
{%- endif %}
{%- if run_linker %}

   Do not create `<name>/<name>.md`, not even as a placeholder, because the linker
   agent `research.{@1}.linker` publishes it from your report.

5. After the write succeeds, register the consolidated report as a durable snapshot so
   the linker agent, `research.{@1}.linker`, can find it:

   sase artifact create -p "<absolute-report-path>" -l "research:<repo-relative-report-path>"

   Use the consolidated report's actual absolute path and its path relative to the
   research repo root, for example `research:202609/<name>/<name>__final.md`. Register
   only the consolidated report, and do not pass `--move`. If registration fails,
   report that failure; do not report the task as fully complete.
{%- endif %}

Final layout:

{{ tree(lead_files) }}
---

%if(should_run={{ image }}) %id(image, clan=research.{@1}) %m:{{ image_model }}
%wait:research.{@1}.final #_queue #fork:research.{@1}.final #research/image
---

%if(should_run={{ run_linker }}) %id(linker, clan=research.{@1}) %m:{{ linker_model }}
%wait:research.{@1}.final {% if image %}%wait:research.{@1}.image {% endif %}{% if audio %}%wait:research.{@1}.audio {% endif %}#_queue

You are the linker agent for a research swarm. The lead researcher,
`research.{@1}.final`, has written a consolidated report on the request below. Your job
is to publish that report as the canonical `<name>.md`: the file readers open, and the
one SASE renders into a Highlights PDF. You are an editor, not a researcher. The new
file must carry exactly the lead's meaning and intent. Do not do research of your own:
add no new claims or sources, settle no open questions, and neither soften nor
strengthen the conclusions or the recommendation. If the lead seems wrong, leave it as
written. The only prose you write yourself is the short research-query summary of the
request that opens the file (step 3).

SASE derives your plan's links from the artifacts you read this turn; use
`sase artifact read` for context you actually used.

Research request (context only; do not research it, but summarize it as the file's
research query in step 3):

{{ prompt }}

The lead researcher's registered report:

#_report_records
{% if image %}
The image agent's registered images:

{% raw %}{% for a in wait.artifacts if a.kind == "image" %}
- wait_name={{ a.wait_name }} label={{ a.label }} vcs_relpath={{ a.vcs_relpath }} path={{ a.path }} ref={{ a.ref }}
{% endfor %}{% endraw %}
{% endif %}
{% if audio %}
The audio agent's narrated edition:

{% raw %}{% if agents is defined %}{% for key, outputs in agents.items() if outputs.audio is defined %}
- agent={{ key }} audio={{ outputs.audio }}
{% endfor %}{% endif %}
{% for a in wait.artifacts if a.kind == "file" and a.label and a.label.startswith("audio:") %}
- wait_name={{ a.wait_name }} label={{ a.label }} path={{ a.path }} ref={{ a.ref }}
{% endfor %}{% endraw %}
{% endif %}
Steps:

1. **Identify the source.** From the registered reports above, find exactly one entry
   with `wait_name` `research.{@1}.final` whose label has the form
   `research:<YYYYMM>/<name>/<name>__final.md`. If there is not exactly one such entry,
   stop and report the missing or ambiguous input instead of guessing. Open the research
   repo with `/sase_repo`, then read the report through its canonical research reference
   (or the `ref` field's `file:<id>` reference if the original has moved) using
   `sase artifact read`. Take `<YYYYMM>/<name>/` from the label, never from the current
   date. Do not read predecessor chat transcripts. Never modify, move, or delete
   `<name>__final.md` or the drafts.

2. **Inventory what must survive.** Before writing, list every finding, recommendation,
   caveat, open question, confidence statement, number, date, version, code block,
   table, and link in the lead's report.
3. **Restructure** the lead's report into a well-thought-out organization:
   - Keep the frontmatter, updating `updated_time` if present.
   - **Open the file in this exact order**, with nothing else between these parts: the frontmatter (if any), one `#` title, the research query,{%- if audio %} the listen card,{%- endif %}{%- if image %} the infographic,{%- endif %} and then the bottom-line section.
   - **Research query.** Directly below the title, add one blockquote that summarizes
     the research request above in one to three sentences, for example
     `> **Research query:** <summary>`. Phrase it as the question or task being
     answered, in the requester's own terms: keep the questions, named subjects, and
     explicit scope or constraints; drop instructions aimed at agents, such as output
     paths, macro or directive syntax, and formatting requests. Summarize what was
     asked, not material the request quotes or attaches. Use a request that is already
     one short sentence verbatim. Never fold findings, answers, or scope the request
     does not state into it. It is not a heading, so it gets no section number and no
     TOC entry.
   {%- if audio %}
   - **Listen card.** Facts come from the `audio` variable of `research.{@1}.audio`
     when `ok` is true. If the variable is missing but an `audio:<episode_id>`
     artifact is listed, recover the facts with `sase listen ls <episode_id> --json`
     (or `sase-listen ls <episode_id> --json`, or `uvx sase-listen ls <episode_id> --json`):
     `audio.duration_s`, chapter count, `script.edition`.
     If `ok` is false or nothing is listed, publish with no card and no `audio:`
     frontmatter, and say so in the final response (never write "audio pending").
     Add this frontmatter mapping (create a frontmatter block if the lead's report
     has none), copying numbers verbatim, never inventing them:

     ```yaml
     audio:
       edition: brief
       duration_s: 250.34
       chapter_count: 3
       episode_id: a-listen-link-for-research-reports-d74298
     ```

     No library path, MP3 path, feed URL, artifact id, or `file:` ref — the research
     repo is public. Insert the card exactly once, directly below the research-query
     blockquote and above the infographic, with the blank lines shown (they make
     GitHub and pandoc parse the inner Markdown):

     ```markdown
     <div class="listen">

     ♫ **Brief audio edition** · 4 min · 3 chapters · [Narration
     script](<name>_narration.md)

     </div>
     ```

     Rules: edition word capitalized (`Brief` / `Full`); minutes =
     `max(1, round(duration_s / 60))`; `1 chapter` singular; drop the chapters
     segment if the count is unknown; include the script segment only when
     `<name>_narration.md` exists beside the report in the research checkout;
     nothing else inside the div; not a heading; not inside the blockquote; never
     a link to an MP3, library path, feed URL, or `highlights://` URI.
   {%- endif %}
   {%- if image %}
   - **Embed the infographic** exactly once, directly above the bottom-line section:
     after the{% if audio %} listen card{% else %} research query{% endif %} and before that section's `##` heading, never further
     down. Use a relative link with descriptive alt text, for example
     `![<alt text>](<name>_infographic.png)`. Locate it by the
     `<name>_infographic.png` convention or the image entries above. Embed only a file
     you have confirmed exists beside the report in your research checkout. If the
     image agent completed without producing one, publish without it (the{% if audio %} listen
     card{% else %} research query{% endif %} then sits directly above the bottom-line section) and say so in the final
     response.
   {%- endif %}
   - **Bottom-line section.** The first `##` section is `## Bottom line` (or
     `## Overview` when the report surveys options rather than giving one answer) and
     gives the answer first.
   - Below it, `##` and `###` sections ordered by the questions a reader will ask, with
     duplicated passages merged.
   - **Never number headings.** The PDF renderer runs pandoc with `--number-sections`,
     so hand-numbered headings render doubly numbered.
   - **No table of contents and no block of jump links.** The PDF already gets a TOC.
   - Keep the lead's wording where it works. Never drop a claim, caveat, or source to
     save space. If the lead's report restates the question or lists its inputs, keep
     those details in a later section; the research query summarizes the request but
     does not replace them.
4. **Validate every link carried over.**
   - Relative links resolve from `<YYYYMM>/<name>/`, and in-document anchors resolve
     against the final headings. Both are hard requirements.
   - Check external URLs with `curl -fsSL -o /dev/null --max-time 20 <url>`, retrying
     a transient failure once. Treat 401, 403, 429, and timeouts as _unverified_ and
     keep those links.
   - Verify repository-file links through a `/sase_repo` checkout, not by fetching
     github.com.
   - Repair a link only when the right target is certain: a followed redirect, a moved
     file, an obvious typo, or a renamed heading. For an unrepairable link, keep its
     text, drop the dead URL, and list it in the final response. **Never search for a
     replacement source.**

5. **Add in-document links** so readers can jump between parts of the file. Add them
   inline and sparingly: from summary points to the sections that back them, from "see
   above" or "see below" phrases, and from mentions of a named option, phase, or
   finding to where it is discussed. Do not link every mention.
   - Every heading used as a link target must start with a letter, contain only
     letters, digits, spaces, and hyphens, and be unique. Its anchor is then the
     lowercased heading with spaces replaced by hyphens, for example
     `[the bottom line](#bottom-line)`. pandoc (the PDF) and GitHub then agree.
   - Move emoji, version numbers, and code out of such headings, into the section's
     first line.
   - When `pandoc` is available, confirm anchors with `pandoc <file> -t html`.

6. **Re-check against the step-2 inventory** and restore anything missing or changed.
   Every URL in `<name>__final.md` must appear in the new file unless it was listed as
   unrepairable. Then confirm the file opens in the step-3 order: title, research query,{%- if audio %} listen card,{%- endif %}{%- if image %} infographic,{%- endif %} bottom-line section.

7. **Write** `<YYYYMM>/<name>/<name>.md` without overwrite. On a collision, stop and
   report it.

8. **Register** it as a durable snapshot:

   sase artifact create -p "<absolute-report-path>" -l "research:<repo-relative-report-path>"

   Use the report's actual absolute path and its path relative to the research repo
   root, for example `research:202609/<name>/<name>.md`. Use no `--move`. If
   registration fails, report it and do not claim full completion.

Final layout:

{{ tree(linker_files) }}
---

%if(should_run={{ audio }}) %id(audio, clan=research.{@1}) %m:{{ audio_model }}
%wait:research.{@1}.final #_queue #fork:research.{@1}.final #research/audio(edition={{ audio_edition }})
