---
description: Write the current research to a new dated file in the research artifact repo.
input:
  - name: report_target
    type: path
    default: null
    description:
      Optional month-relative markdown report path. When set, write exactly this file
      and fail visibly if it already exists.
  - name: suffix
    type: word
    default: null
    description:
      Optional filename suffix identifier (e.g. `a` or `b`). Omit it or set it to
      `false` to disable suffixing; another identifier requests `__<suffix>.md`.
      Ignored when `report_target` is provided, since that names the file exactly.
  - name: diagrams
    type: bool
    default: false
    description:
      Add one or more useful Mermaid diagrams to the report, chosen, drawn, and
      render-checked with the `/mermaid_diagrams` skill. Off by default.
---

{% if report_target %}
Write this research to exactly this report file:

$(sase repo path research --ensure)/$(date +%Y%m)/{{ report_target }}

Create parent directories if needed. Create the report without overwrite: if the file
already exists, stop and report the collision visibly instead of replacing it.
{% elif suffix and suffix != 'false' %}
Write this research to a new markdown file under the $(sase repo path research --ensure)/$(date +%Y%m)/ directory.
Choose a descriptive filename stem yourself, but the filename MUST end with the
`__{{ suffix }}` suffix, i.e. `<stem>__{{ suffix }}.md` (double underscore before the
suffix). Create the report without overwrite: if the exact file already exists, pick a
different stem instead of replacing it.
{% else %}
Write this research to a new markdown file under the $(sase repo path research --ensure)/$(date +%Y%m)/ directory.
{% endif %}
{%- if diagrams %}

Add one or more useful Mermaid diagrams to this report. Load your `/mermaid_diagrams`
skill before drafting any figure, and follow it to choose, draw, style, and render-check
every diagram. If that skill is not deployed on this host, read the same guide with
`sase macro show skill/mermaid_diagrams --format raw` (or
`sase macro show /mermaid_diagrams --format raw`) and use whichever form works.

- Choose figures by the skill's rules: name the reader question each figure answers,
  prefer what the report's conclusion depends on, and draw only actors, steps, and
  relations the report itself states. Add at least one figure, usually one to three and
  never more than five. Even a survey gets one: draw the strongest candidate the report
  supports, such as its decision rule or comparison structure, scoped to the part the
  conclusion depends on.
- Place each figure directly after the paragraph, or after the whole list, whose
  question it answers. Never put a figure directly under a heading or inside a list or
  blockquote. Follow each fence with its one-sentence caption as one italic line.
- Keep render scratch files (`.mmd`, SVG, PNG, and configs) outside the research
  checkout; only the report belongs there. Each fence in the report must be
  byte-identical to the source that passed the skill's render check.
- Finish the diagrams before you register the report below, so the registered snapshot
  includes them.
- Diagram trouble never blocks the report. If no Mermaid CLI renders on this host, write
  and register the report without diagrams and say so in your final response.
- In your final response, list each diagram you added with the reader question it
  answers.
{%- endif %}

After the write succeeds, register the report as a durable snapshot:

sase artifact create -p "<absolute-report-path>" -l "research:<repo-relative-report-path>"

Use the report's actual absolute path and its path relative to the research repo root
(for example
`research:202609/topic{% if suffix and suffix != 'false' %}__a{% endif %}.md`),
including any subdirectory the steps above put it in. Do not derive the label from
the current month, the clock, or a guessed name.
Do not pass `--move`; the source stays in the research repo for later reorganization. If
registration itself fails, report that failure — do not report the research task as
fully complete.
