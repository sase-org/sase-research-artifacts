# Configuration

## Requirements

- Python 3.12+
- `sase>=0.17.0` (the first release with the `sase_artifact_refs` / `sase_file_hooks`
  provider registry). That floor has not reached PyPI yet; local and CI installs
  route `sase` to a coordinated source checkout instead of asking the index for it
  (see [README Development](../README.md#development)).

## Enabling the `research` ref provider

Point a project's `research` sidecar role at this plugin with a plugin-qualified
`use:` (`<distribution>@<id>`). A bare id fails soft with `missing_use_prefix`:

```yaml
repos:
  sidecar:
    custom:
      research:
        ref:
          use: sase-research-artifacts@research
```

Override individual fields without repeating the whole spec:

```yaml
repos:
  sidecar:
    custom:
      research:
        ref:
          use: sase-research-artifacts@research
          inventory:
            globs: ["20*/**/*.md", "!20*/scratch/**"]
```

Merge rules: scalars replace, mappings deep-merge, and list-valued fields (like
`inventory.globs` or pane row fields) **replace rather than concatenate** the provider's
base list. `use:` and an equivalent fully-inline spec always normalize to byte-identical
effective specs and provider digests; pane-only edits are preserved for Python
presentation and intentionally stay out of the Rust provider digest.

The base inventory deliberately excludes generated infographic companion Markdown pages,
including `*_infographic.md` and disambiguated binary pages such as `*.png.md`, so link
companions do not appear as research reports.

An unresolvable `use:` (the plugin is not installed) fails soft: the role is dropped
with a `missing_ref_provider` diagnostic rather than raising on the launch path. A
linked-repo clone of `sase-research-artifacts` does not install the distribution or register its
entry points -- install the package itself.

## Enabling the `research-highlights` file hook

```yaml
file_hooks:
  - use: sase-research-artifacts@research-highlights
    command: bob highlights create --include-id
```

The provider template supplies `description`, `filters` (`sidecars: [research]`,
`producers: [commit, sdd, finalizer]`, `path_globs: ["20*/**/*.md",
"!20*/*/*__*.md"]`, `agent_name_globs: ["!research.*.cld", "!research.*.cdx"]`,
`ops: [ADD]`), and `timeout: 120s`. `command` is deliberately absent from the template
and listed as `required`: the policy is portable, but the executable is local to your
machine. Omitting `command` fails soft with a diagnostic naming the missing field rather
than running an unset command.

The producer restriction keeps committed-file routes and finalizer repair while
skipping artifact-copy dispatch. Artifact dispatch executes against durable
content-addressed copies whose basenames can carry digest suffixes, which would leak
into Bob's derived PDF basename and marker id.

`name` is not part of the template either -- it defaults to the provider id
(`research-highlights`) unless you override it locally.

## Default Config

Installing this plugin also contributes, through the `sase_config` entry point:

- Model aliases `research_a` (primary researcher), `research_b` (second-opinion
  researcher), and `image` (infographic agent), all in the `researchers` bucket. The
  research-swarm lead launches through SASE's built-in `@xlarge` alias.
- The `research` tribe's display config (icon, color, description).

These are ordinary default-config values and are overridden by project or user config
through normal layer precedence.
