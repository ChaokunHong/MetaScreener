"""Detect and mark sections in academic paper full text.

Identifies common paper sections (Abstract, Methods, Results, Discussion)
and inserts markdown markers for LLM consumption. Optionally strips
the References section to save tokens.
"""
from __future__ import annotations

import re

# Optional numbering prefix: "2.", "2.1", "II.", "III.", etc.
_NUM_PREFIX = r"(?:\d+(?:\.\d+)*\.?\s+|[IVXLCDM]+\.?\s+)?"

# Section heading patterns (case-insensitive, must be on their own line)
_SECTION_PATTERNS: list[tuple[str, str]] = [
    (rf"(?i)^{_NUM_PREFIX}(abstract|summary)\s*$", "## ABSTRACT"),
    (rf"(?i)^{_NUM_PREFIX}(introduction|background)\s*$", "## INTRODUCTION"),
    (
        rf"(?i)^{_NUM_PREFIX}(methods?|materials?\s+and\s+methods?|study\s+design|"
        r"patients?\s+and\s+methods?|experimental\s+design)\s*$",
        "## METHODS",
    ),
    (rf"(?i)^{_NUM_PREFIX}(results?|findings?)\s*$", "## RESULTS"),
    (
        rf"(?i)^{_NUM_PREFIX}(discussion|discussion\s+and\s+conclusions?)\s*$",
        "## DISCUSSION",
    ),
    (rf"(?i)^{_NUM_PREFIX}(conclusions?|concluding\s+remarks?)\s*$", "## CONCLUSION"),
    (rf"(?i)^{_NUM_PREFIX}(references?|bibliography|cited\s+literature)\s*$", "## REFERENCES"),
]

_REFERENCES_RE = re.compile(
    r"(?i)\n## REFERENCES\n.*", re.DOTALL
)


def detect_and_mark_sections(
    text: str,
    strip_references: bool = True,
) -> str:
    """Detect academic paper sections and insert markdown markers.

    Scans each line for common section headings and replaces them
    with standardised markdown markers (e.g., ``## METHODS``).
    Optionally removes the References section entirely to save tokens.

    Args:
        text: Full paper text.
        strip_references: If True, remove everything from the References
            section onward. Default True.

    Returns:
        Text with section markers inserted (and References stripped
        if requested).
    """
    if not text:
        return text

    lines = text.split("\n")
    marked_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        matched = False
        for pattern, marker in _SECTION_PATTERNS:
            if re.match(pattern, stripped):
                marked_lines.append(f"\n{marker}")
                matched = True
                break
        if not matched:
            marked_lines.append(line)

    result = "\n".join(marked_lines)

    if strip_references:
        result = _REFERENCES_RE.sub("", result)

    return result.strip()
