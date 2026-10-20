---
description:
  Launch independent per-provider research agents, then have a lead researcher extend
  and consolidate their findings. Optionally generate an infographic, Mermaid diagrams,
  and/or a narrated audio edition; `image=true`, `diagrams=true`, or `audio=true`
  implies a linker agent that publishes the canonical report (with a listen card when
  audio succeeds).
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
  - name: diagrams
    type: bool
    default: null
    description:
      Propose validated Mermaid diagrams after the lead researcher finishes. When
      null, follows `image`. `diagrams=true` implies the image segment and the
      linker. `image=true diagrams=false` keeps the infographic without diagrams.
  - name: linker
    type: bool
    default: false
    description:
      Run a linker agent after the lead researcher (and after the image agent when
      the image segment runs, and after the audio agent when `audio=true`). The lead
      then writes `<name>__final.md` while the linker publishes `<name>.md`. The
      linker always runs when `image=true`, `diagrams=true`, or `audio=true`.
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
{%- set run_diagrams = image if diagrams is none else diagrams -%}
{%- set run_visual = image or run_diagrams -%}
{%- set run_linker = linker or run_visual or audio -%}
{%- set lead_report = "<name>__final.md" if run_linker else "<name>.md" -%}
{%- set drafts = [] -%}
{%- for r in researchers %}{% set _ = drafts.append("<name>__" ~ r.short ~ ".md") %}{% endfor -%}
{%- set narration = ["<name>_narration.md"] if audio else [] -%}
{%- set lead_files = drafts + [lead_report] + narration -%}
{%- set linker_files = drafts + ["<name>__final.md"] + (["<name>_infographic.png"] if image else []) + (["<name>.diagrams.md (optional)"] if run_diagrams else []) + ["<name>.md"] + narration -%}
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

When you author or carry over Mermaid diagrams, load `/mermaid_diagrams` before
drafting, even when no image or diagrams companion runs. The skill has the shared
figure-selection, styling, and PDF-render review rules. If the provider skill is not
deployed, verify the edited plugin's guide with `sase macro show skill/mermaid_diagrams --format raw` (or
`sase macro show /mermaid_diagrams --format raw`) and use the form this host supports.
This guidance does not enable a companion diagrams agent.

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

%if(should_run={{ run_visual }}) %id(image, clan=research.{@1}) %m:{{ image_model }}
%wait:research.{@1}.final #_queue #fork:research.{@1}.final{% if image %} #research/image{% endif %}
{%- if run_diagrams %}

The lead researcher's registered report:

#_report_records

#research/diagrams
{%- endif %}
---

%if(should_run={{ run_linker }}) %id(linker, clan=research.{@1}) %m:{{ linker_model }}
%wait:research.{@1}.final {% if run_visual %}%wait:research.{@1}.image {% endif %}{% if audio %}%wait:research.{@1}.audio {% endif %}#_queue

You are the linker agent for a research swarm. The lead researcher,
`research.{@1}.final`, has written a consolidated report on the request below. Your job
is to publish that report as the canonical `<name>.md`: the file readers open, and the
one SASE renders into a Highlights PDF. You are an editor, not a researcher. The new
file must carry exactly the lead's meaning and intent. Do not do research of your own:
add no new claims or sources, settle no open questions, and neither soften nor
strengthen the conclusions or the recommendation. If the lead seems wrong, leave it as
written. The only prose you write yourself is the short research-query summary of the
request that opens the file (step 3).{%- if run_diagrams %} The only other content you
add is the image agent's diagrams and captions, copied verbatim, plus a figure anchor
and one short reference sentence for each diagram you place (step 3).{%- endif %}

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
{% if run_diagrams %}
The image agent's diagram proposals:

{% raw %}{% if agents is defined %}{% for key, outputs in agents.items() if outputs.diagrams is defined %}
- agent={{ key }} diagrams={{ outputs.diagrams }}
{% endfor %}{% endif %}
{% for a in wait.artifacts if a.label and a.label.startswith("diagrams:") %}
- wait_name={{ a.wait_name }} label={{ a.label }} path={{ a.path }} ref={{ a.ref }}
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
   `<name>__final.md` or the drafts{%- if run_diagrams %} or `<name>.diagrams.md`{%- endif %}.
   {%- if run_diagrams %}
   Read the `diagrams` variable of `research.{@1}.image`. Only when its `status` is
   `ready`, take exactly one listed `diagrams:` entry from `wait_name`
   `research.{@1}.image` whose label is
   `diagrams:<YYYYMM>/<name>/<name>.diagrams.md` for the lead's own
   `<YYYYMM>/<name>/`. Read it with `sase artifact read`, and confirm its `source`
   equals the lead's label. Publish with no proposed diagrams, and say why in the
   final response, if the status is `none` or `failed`, the variable is missing, the
   manifest entry is missing or ambiguous, or the source does not match. Diagram
   problems never stop publication. The manifest's `question` and `review` are the
   image agent's audit notes: never copy them into the report.
   {%- endif %}

2. **Inventory what must survive.** Before writing, list every finding, recommendation,
   caveat, open question, confidence statement, number, date, version, code block,
   table (record its cells; step 3 converts each one into a list), and link in the
   lead's report.{%- if run_diagrams %} For each manifest diagram, record its ID against
   the one lead block (paragraph or list item) that contains its `anchor`. Mark a
   diagram whose anchor matches zero or several blocks as omitted. Mark every diagram after the fifth in manifest order as omitted (over the cap).{%- endif %}
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
   - **No tables.** The PDF renderer (pandoc → XeLaTeX) prints tables with equal-width
     columns, cramped wrapped cells, and rows that jump pages. Convert every table in the
     lead's report (pipe, grid, simple, multiline, or HTML) into a list with one item per
     row, keeping every cell's content:
     - Two columns: `- **<first cell>:** <second cell>`.
     - Three or more columns: a bullet whose first line is the row's identifying cell in
       bold (merge an ID column into it, e.g. `- **A1. Restart exactly once**`), then one
       nested bullet per remaining non-empty cell, `- *<Column header>:* <cell>`, in column
       order. Labels go in italics so bold inside a value stays distinct.
     - Ordered rows (phases, steps, ranks, tiers): the same shapes as a numbered list,
       keeping the original numbers.
     - Grouped rows (a blank first cell continues the group above): nest them under one
       bullet for the group.
     - Rows whose cells are all a few words: one line,
       `- **<row>:** <header> <value> · <header> <value> · …`.
     - Numbers: keep units, periods, denominators, and the difference between zero,
       unknown, and not applicable.
     - Long code in a cell: a fenced code block inside the list item.
     - Only when the rows are about six or fewer major named options the report discusses
       at length: one `###` section per option holding the same italic-labelled bullets.
       Never turn a row into a `####` heading. Turn a table caption into a one-line lead-in
       sentence. Put a blank line before every list (pandoc otherwise merges it into the
       paragraph above). Indent nested bullets 2 spaces under `- ` and
       3 spaces under `1. `. Write URLs as `[text](url)` or `<url>`, never bare. Do not
       substitute a definition list (`Term` then `: definition`), an HTML table, a grid
       or simple table, a table in a code block, a callout or `:::` div, raw LaTeX, or
       an image, or a diagram. Never drop a cell, merge two rows, or add totals, rankings, or
       conclusions the table did not state.
   - Keep the lead's wording where it works. Never drop a claim, caveat, or source to
     save space. If the lead's report restates the question or lists its inputs, keep
     those details in a later section; the research query summarizes the request but
     does not replace them.
   {%- if run_diagrams %}
   - **Place proposed diagrams.** After restructuring, insert each fence byte-for-byte
     directly after the block that now carries the tagged content, even if that content
     was reordered, merged, or converted from a table into a list. Only that figure's
     reference sentence may sit between the block and its fence. Follow the fence with
     the caption as one italic line, with blank lines around both, and wrap the fence
     and caption in the figure anchor described below. Then check that the surrounding
     final text still states the `illustrates` point and that no box or edge contradicts
     it. Omit the diagram otherwise. Never place a diagram in the fixed opening
     sequence, directly under a heading, inside a list or blockquote (put it after the
     whole list), or in an appendix; bottom-line content goes at the end of that
     section; two diagrams on one block go in manifest order. Never edit, redraw,
     merge, or invent a diagram. A private scratch marker such as `<!-- D:<id> -->` may
     be used in the working draft but must be gone before writing.
   - **Anchor every placed figure.** Wrap each placed fence and its caption, and
     nothing else, in `<div id="figure-<id>">` and `</div>`, using its manifest `## <id>`.
     Convert the ID to lowercase letters, digits, and hyphens, replacing each run of
     other characters with one hyphen. Keep the resulting ID unique in the file; if it
     matches a heading anchor or another figure ID, append `-2`, `-3`, and so on. Leave
     a blank line after the opening tag and before the closing tag so GitHub and pandoc
     parse the fence and caption as Markdown. The wrapper is the figure's link target
     on both reading surfaces: GitHub keeps its ID for jumps, and the Highlights PDF
     gives it return links. Use this shape:

     ````markdown
     <div id="figure-publication-order">

     <the manifest's mermaid fence, byte-for-byte>

     _The linker publishes once, after every companion finishes._

     </div>
     ````

     Never put an ID or attribute on the fence itself, and never substitute an `<a>`
     anchor or a heading. This wrapper and the listen card are the only HTML blocks you
     write. The table rule that forbids `:::` divs is about table substitutes and does
     not cover this figure wrapper.
   - **Reference every placed figure.** Write exactly one short sentence per placed
     figure and link it with `[<link text>](#figure-<id>)`, using the final unique ID,
     so every published figure is referenced. Tell the reader what the figure makes
     visible that the prose alone does not, such as a path, order, branch, or handoff.
     Build the sentence from the manifest's `illustrates` point, phrased in the
     surrounding text's terms. Never write a bare pointer such as "See the diagram below."
     The sentence is a pointer, not a finding: add no claim, number, actor,
     step, or causal link that `illustrates` and the surrounding final text do not
     already state; keep conditional wording conditional and proposed designs distinct
     from implemented ones. Do not repeat the caption word for word. Name the figure in
     the link text, for example `the publication-order diagram`.
     Never use "here", "this", or a figure number in the link text. Keep it to about
     12 to 30 words of plain prose. It is
     not italic, a heading, or a list item, and never goes inside the figure's `<div>`,
     its caption, or a blockquote. When the figure directly follows the paragraph that
     carries its anchor, make the reference sentence end that paragraph. Otherwise,
     give it its own short paragraph directly above the figure's `<div>`; this happens
     when the anchor sits in a list (so the figure follows the whole list) or when the
     figure closes the bottom-line section. Two figures after one block get one sentence
     each, in manifest order. If you omit a figure, delete its sentence too; no link may
     point to an unpublished figure. For example: `… so the link must be in the linker's first commit. [The publication-order diagram](#figure-publication-order) traces why the linker waits for every companion agent: the PDF hook fires only once, on the ADD of name.md.`
   {%- endif %}
4. **Validate every link carried over.**
   - Relative links resolve from `<YYYYMM>/<name>/`, and in-document anchors resolve
     against the final headings{%- if run_diagrams %} and figure anchors{%- endif %}. Both are hard requirements.
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
   {%- if run_diagrams %}
   - A summary point that discusses a figure's content may also link sparingly to its
     `figure-<id>` anchor. Always link a figure through that anchor, never through a
     nearby heading.
   {%- endif %}

6. **Re-check against the step-2 inventory** and restore anything missing or changed.
   Every URL in `<name>__final.md` must appear in the new file unless it was listed as
   unrepairable. Then confirm the file opens in the step-3 order: title, research query,{%- if audio %} listen card,{%- endif %}{%- if image %} infographic,{%- endif %} bottom-line section.
   Confirm every cell of every table in the lead's report appears in the new file. When
   `pandoc` is available, confirm no table survives:
   `pandoc <file> -f markdown -t json | grep -o -i -E '"t":"Table"|"t":"RawBlock","c":\["html","<table' | wc -l`
   prints `0`. Every Mermaid diagram from the lead's report is still present.
   {%- if run_diagrams %} Every manifest diagram appears exactly once, byte-identical,
   or is named as omitted. Every accepted diagram sits inside exactly one figure-anchor
   `<div>` holding only its fence and caption, and its reference sentence links to it:
   `grep -c '^<div id="figure-' <file>` equals the number of accepted diagrams; every
   `(#figure-` link names an ID that exists in the file; and `pandoc <file> -t html`
   shows each `id="figure-<id>"`.{%- endif %} The published mermaid fence count equals the
   lead's count plus the number of accepted proposed diagrams.
   {%- if run_diagrams %} In the final response, list accepted diagram IDs with their
   `figure-<id>` anchors and omitted IDs with reasons. Never write "diagrams pending".{%- endif %}

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
