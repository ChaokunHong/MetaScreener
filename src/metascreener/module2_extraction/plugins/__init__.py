"""Domain plugin system for extraction."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from metascreener.module2_extraction.plugins.models import (
    PluginConfig,
    PluginRule,
    TerminologyEntry,
)
from metascreener.module2_extraction.plugins.prompt_builder import load_prompt_fragments
from metascreener.module2_extraction.plugins.rule_builder import (
    RuleCallback,
    build_rule_callbacks,
)
from metascreener.module2_extraction.plugins.terminology import TerminologyEngine

log = structlog.get_logger()
_PLUGINS_DIR = Path(__file__).parent

@dataclass
class LoadedPlugin:
    """A fully loaded plugin with all resources initialised.

    Attributes:
        config: Parsed plugin configuration.
        terminology_engines: Mapping from terminology file stem to engine.
        rule_callbacks: List of compiled rule callback functions.
        prompt_fragments: Mapping from prompt stem to Jinja2 template text.
    """

    config: PluginConfig
    terminology_engines: dict[str, TerminologyEngine] = field(default_factory=dict)
    rule_callbacks: list[RuleCallback] = field(default_factory=list)
    prompt_fragments: dict[str, str] = field(default_factory=dict)

def load_plugin(plugin_id: str) -> LoadedPlugin:
    """Load a plugin by its identifier.

    Scans ``plugins/{plugin_id}/`` for a ``plugin.yaml`` manifest, then
    loads terminology YAML files, rule YAML files, and Jinja2 prompt
    fragments from the expected sub-directories.

    Args:
        plugin_id: Identifier matching the plugin directory name (e.g. ``"amr_v1"``).

    Returns:
        A fully populated :class:`LoadedPlugin` instance.

    Raises:
        FileNotFoundError: If the plugin directory or manifest does not exist.
    """
    plugin_dir = _PLUGINS_DIR / plugin_id
    manifest_path = plugin_dir / "plugin.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Plugin not found: {plugin_id} (looked in {plugin_dir})"
        )

    with open(manifest_path, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    config = PluginConfig(**raw)

    # Load terminology engines
    terminology_engines: dict[str, TerminologyEngine] = {}
    term_dir = plugin_dir / "terminology"
    if term_dir.exists():
        for yaml_path in sorted(term_dir.glob("*.yaml")):
            name = yaml_path.stem
            with open(yaml_path, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f)
            entries = [TerminologyEntry(**e) for e in data.get("entries", [])]
            terminology_engines[name] = TerminologyEngine(entries)

    # Load validation rules
    all_rules: list[PluginRule] = []
    rules_dir = plugin_dir / "rules"
    if rules_dir.exists():
        for yaml_path in sorted(rules_dir.glob("*.yaml")):
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for rule_data in data.get("rules", []):
                all_rules.append(PluginRule(**rule_data))
    rule_callbacks = build_rule_callbacks(all_rules)

    # Load prompt fragments
    prompt_fragments = load_prompt_fragments(plugin_dir / "prompts")

    log.info(
        "plugin_loaded",
        plugin_id=config.plugin_id,
        terminology=len(terminology_engines),
        rules=len(all_rules),
        prompts=len(prompt_fragments),
    )
    return LoadedPlugin(
        config=config,
        terminology_engines=terminology_engines,
        rule_callbacks=rule_callbacks,
        prompt_fragments=prompt_fragments,
    )

def detect_plugin(
    *,
    column_names: list[str] | None = None,
    keywords: list[str] | None = None,
) -> str | None:
    """Detect the most appropriate plugin for a dataset.

    Scans all plugin directories, scores each against the supplied column
    names and/or keywords, and returns the plugin ID with the highest score
    if it meets the minimum threshold.

    Args:
        column_names: Column names present in the dataset (keyword-only).
        keywords: Free-text keywords found in the dataset (keyword-only).

    Returns:
        Plugin ID string if a confident match is found (score >= 2), or
        ``None`` if no plugin scores above the threshold.
    """
    best_id: str | None = None
    best_score = 0

    for plugin_dir in _PLUGINS_DIR.iterdir():
        manifest = plugin_dir / "plugin.yaml"
        if not manifest.exists():
            continue
        with open(manifest, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        score = 0
        detect_cols = {c.lower() for c in raw.get("auto_detect_columns", [])}
        detect_kws = {k.lower() for k in raw.get("auto_detect_keywords", [])}

        if column_names:
            score += len({c.lower() for c in column_names} & detect_cols)
        if keywords:
            score += len({k.lower() for k in keywords} & detect_kws)

        if score > best_score:
            best_score = score
            best_id = raw.get("plugin_id")

    if best_score >= 2:
        return best_id
    return None
