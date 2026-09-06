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
      Optional filename suffix identifier (e.g. `a` or `b`). When set and
      `report_target` is not, the chosen report filename must end with `__<suffix>.md`.
      Ignored when `report_target` is provided, since that names the file exactly.
---

{% if report_target %}
Write this research to exactly this report file:

$(sase repo path research --ensure)/$(date +%Y%m)/{{ report_target }}

Create parent directories if needed. Create the report without overwrite: if the file
already exists, stop and report the collision visibly instead of replacing it.
{% elif suffix %}
Write this research to a new markdown file under the $(sase repo path research --ensure)/$(date +%Y%m)/ directory.
Choose a descriptive filename stem yourself, but the filename MUST end with the
`__{{ suffix }}` suffix, i.e. `<stem>__{{ suffix }}.md` (double underscore before the
suffix). Create the report without overwrite: if the exact file already exists, pick a
different stem instead of replacing it.
{% else %}
Write this research to a new markdown file under the $(sase repo path research --ensure)/$(date +%Y%m)/ directory.
{% endif %}

After the write succeeds, register the report as a durable snapshot:

sase artifact create -p "<absolute-report-path>" -l "research:<repo-relative-report-path>"

Use the report's actual absolute path and its path relative to the research repo root
(for example `research:202609/topic__a.md`), including any subdirectory the steps above
put it in. Do not derive the label from the current month, the clock, or a guessed name.
Do not pass `--move`; the source stays in the research repo for later reorganization. If
registration itself fails, report that failure — do not report the research task as
fully complete.
