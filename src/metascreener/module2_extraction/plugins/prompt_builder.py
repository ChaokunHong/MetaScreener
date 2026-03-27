"""Loads Jinja2 prompt fragments from plugin directories."""
from __future__ import annotations

from pathlib import Path

import structlog

log = structlog.get_logger()


def load_prompt_fragments(prompts_dir: Path) -> dict[str, str]:
    """Load all Jinja2 prompt fragments from a plugin's prompts directory.

    Args:
        prompts_dir: Path to the prompts directory inside a plugin folder.

    Returns:
        Dictionary mapping stem name to template content. Empty if directory
        does not exist or contains no .jinja2 files.
    """
    fragments: dict[str, str] = {}
    if not prompts_dir.exists():
        return fragments
    for path in sorted(prompts_dir.glob("*.jinja2")):
        fragments[path.stem] = path.read_text(encoding="utf-8")
    log.info(
        "prompt_fragments_loaded",
        count=len(fragments),
        names=list(fragments.keys()),
    )
    return fragments
