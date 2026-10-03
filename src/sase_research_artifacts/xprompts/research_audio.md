---
name: research/audio
description: Narrate a research report as a chaptered MP3 audio edition with sase-listen.
input:
  - name: edition
    type: word
    default: "brief"
    description:
      "Narration edition: brief (about 4 minutes, the default) or full (about 16
      minutes) -- the supported guide-backed authoring choices. Passed to
      `sase-listen guide --edition`."
  - name: rewrite
    type: bool
    default: false
    description:
      Rewrite the `<stem>_narration.md` script even when one already exists.
---

Narrate a research report as an audio edition MP3.

## 1. Find the report

- When invoked with a `@research:` ref, read the report with `sase artifact read`.
- When forked from a swarm lead, use the report you wrote. Prefer the published
  `<name>.md`, and fall back to `<name>__final.md`.
- The research checkout is `$(sase repo path research --ensure)`.

## 2. Choose the CLI

Use `sase-listen` if `command -v sase-listen` succeeds, otherwise `uvx sase-listen`.
This plugin never depends on `sase-listen`; the CLI is invoked at runtime only.

## 3. Write or reuse the script

The script is `<stem>_narration.md` next to the report, with `__final` stripped from
the stem, following the `research_image.md` stem rule (so `topic__final.md` becomes
`topic_narration.md`; other stems are unchanged). Create it without overwrite.

- If it exists and `rewrite` is false, reuse it: an existing script is reused
  unless direct `#research/audio(..., rewrite=true)` is requested. These
  edition defaults govern newly authored scripts.
- Otherwise run `sase-listen guide --edition {{ edition }}` and write the script
  following it exactly, with `source`, `source_blob`, `date`, `kind: research`,
  `edition: {{ edition }}`, and `cover` when `<stem>_infographic.png` exists.
- Run `sase-listen lint <script> --source <report>` (the `lint --source`
  number-fidelity check) until it is clean.

## 4. Render

Render with `sase tool run -- sase-listen render <script> --json` (the `render --json`
single-object stdout contract). If the render
approaches the inline ceiling, hand it to `/sase_monitor`.

## 5. Deliver

Register the finished MP3 with
`sase artifact create -p <audio_path> -l "Audio edition: <title>"`. The MP3 rides
the completion notification to Telegram.

## 6. Report

Report the duration, chapters, approximate cost, and whether it was published to the
feed.

On a render failure, report the error code and hint, and never switch narrators
silently.
