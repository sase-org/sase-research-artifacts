"""New-first sase macro imports with legacy xprompt fallbacks.

Tests that run against sase master resolve the renamed ``sase.macro`` APIs
first and fall back to the retired ``sase.xprompt`` spellings, so the suite
also passes against older sase floors. The published-minimum smoke
(``.github/workflows/publish.yml``) and ``test_ci_install_contract.py``
intentionally keep the legacy import names.
"""

from __future__ import annotations

from typing import Any

try:
    from sase.macro.loader_sources import load_macros_from_plugins
except ImportError:  # older sase without the macro rename
    from sase.xprompt.loader_sources import (  # type: ignore[no-redef]
        load_xprompts_from_plugins as load_macros_from_plugins,
    )

try:
    from sase.macro.processor import expand_single_macro
except ImportError:  # older sase without the macro rename
    from sase.xprompt.processor import (  # type: ignore[no-redef]
        expand_single_xprompt as expand_single_macro,
    )

try:
    from sase.macro import render_toplevel_jinja2
except ImportError:  # older sase without the macro rename
    from sase.xprompt import render_toplevel_jinja2  # type: ignore[no-redef]

try:
    from sase.macro.models import UNSET
except ImportError:  # older sase without the macro rename
    from sase.xprompt.models import UNSET  # type: ignore[no-redef]

try:
    from sase.macro.runtime_context import bind_runtime_template_vars
except ImportError:  # older sase without the macro rename
    from sase.xprompt.runtime_context import (  # type: ignore[no-redef]
        bind_runtime_template_vars,
    )

try:
    from sase.agent.macro_swarm import expand_macro_swarms_with_metadata
except ImportError:  # older sase without the macro rename
    from sase.agent.xprompt_swarm import (  # type: ignore[no-redef]
        expand_xprompt_swarms_with_metadata as expand_macro_swarms_with_metadata,
    )

try:
    from sase.macro.loader_parsing import parse_yaml_front_matter
except ImportError:  # older sase without the macro rename
    from sase.xprompt.loader_parsing import (  # type: ignore[no-redef]
        parse_yaml_front_matter,
    )


def render_generated_skill_targets(
    skill_macros: list[Any],
) -> list[Any] | None:
    """Use the host's read-only skill renderer when this SASE version exposes it."""
    try:
        from sase.main import init_skills_handler
    except ImportError:
        return None

    renderer = getattr(init_skills_handler, "render_skill_targets", None)
    if not callable(renderer):
        return None
    return renderer(
        skill_macros,
        provider_filter="codex",
        use_chezmoi=False,
        use_prettier=False,
    )

__all__ = [
    "UNSET",
    "bind_runtime_template_vars",
    "expand_macro_swarms_with_metadata",
    "expand_single_macro",
    "load_macros_from_plugins",
    "parse_yaml_front_matter",
    "render_toplevel_jinja2",
    "render_generated_skill_targets",
]
