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
# English patterns
_EN_PATTERNS: list[tuple[str, str]] = [
    (rf"(?i)^{_NUM_PREFIX}(abstract|summary|synopsis)\s*$", "## ABSTRACT"),
    (rf"(?i)^{_NUM_PREFIX}(introduction|background|overview|context)\s*$", "## INTRODUCTION"),
    (
        rf"(?i)^{_NUM_PREFIX}(methods?|materials?\s+and\s+methods?|study\s+design|"
        r"patients?\s+and\s+methods?|experimental\s+design|"
        r"experimental\s+procedures?|experimental\s+section|"
        r"subjects?\s+and\s+methods?|data\s+and\s+methods?|"
        r"methodology|statistical\s+analysis|"
        r"data\s+collection|study\s+population|"
        r"participants?\s+and\s+methods?|procedures?)\s*$",
        "## METHODS",
    ),
    (rf"(?i)^{_NUM_PREFIX}(results?|findings?|observations?|outcomes?)\s*$", "## RESULTS"),
    (
        rf"(?i)^{_NUM_PREFIX}(discussion|discussion\s+and\s+conclusions?|"
        r"interpretation|general\s+discussion)\s*$",
        "## DISCUSSION",
    ),
    (
        rf"(?i)^{_NUM_PREFIX}(conclusions?|concluding\s+remarks?|"
        r"summary\s+and\s+conclusions?|implications?)\s*$",
        "## CONCLUSION",
    ),
    (
        rf"(?i)^{_NUM_PREFIX}(references?|bibliography|cited\s+literature|"
        r"literature\s+cited|works?\s+cited)\s*$",
        "## REFERENCES",
    ),
]

# CJK patterns (Chinese, Japanese, Korean — no _NUM_PREFIX needed)
_CJK_PATTERNS: list[tuple[str, str]] = [
    # Chinese
    (r"^(摘\s*要|提\s*要)\s*$", "## ABSTRACT"),
    (r"^(引\s*言|前\s*言|背\s*景|绪\s*论)\s*$", "## INTRODUCTION"),
    (r"^(方\s*法|材料与方法|研究方法|实验方法|对象与方法|资料与方法)\s*$", "## METHODS"),
    (r"^(结\s*果|研究结果)\s*$", "## RESULTS"),
    (r"^(讨\s*论|分析与讨论)\s*$", "## DISCUSSION"),
    (r"^(结\s*论|结\s*语|小\s*结)\s*$", "## CONCLUSION"),
    (r"^(参考文献|引用文献|文\s*献)\s*$", "## REFERENCES"),
    # Japanese
    (r"^(抄録|要旨|概要)\s*$", "## ABSTRACT"),
    (r"^(緒言|はじめに|序論)\s*$", "## INTRODUCTION"),
    (r"^(方法|研究方法|対象と方法)\s*$", "## METHODS"),
    (r"^(結果)\s*$", "## RESULTS"),
    (r"^(考察)\s*$", "## DISCUSSION"),
    (r"^(結論|おわりに)\s*$", "## CONCLUSION"),
    (r"^(引用文献|参考文献|文献)\s*$", "## REFERENCES"),
]

# European language patterns (German, French, Spanish, Portuguese)
_EU_PATTERNS: list[tuple[str, str]] = [
    # German
    (rf"(?i)^{_NUM_PREFIX}(zusammenfassung|abstrakt)\s*$", "## ABSTRACT"),
    (rf"(?i)^{_NUM_PREFIX}(einleitung|hintergrund)\s*$", "## INTRODUCTION"),
    (rf"(?i)^{_NUM_PREFIX}(methoden|methodik|material\s+und\s+methoden)\s*$", "## METHODS"),
    (rf"(?i)^{_NUM_PREFIX}(ergebnisse)\s*$", "## RESULTS"),
    (rf"(?i)^{_NUM_PREFIX}(diskussion)\s*$", "## DISCUSSION"),
    (rf"(?i)^{_NUM_PREFIX}(schlussfolgerung|fazit)\s*$", "## CONCLUSION"),
    (rf"(?i)^{_NUM_PREFIX}(literatur|literaturverzeichnis)\s*$", "## REFERENCES"),
    # French
    (rf"(?i)^{_NUM_PREFIX}(r[ée]sum[ée])\s*$", "## ABSTRACT"),
    (rf"(?i)^{_NUM_PREFIX}(m[ée]thodes?|mat[ée]riel\s+et\s+m[ée]thodes?)\s*$", "## METHODS"),
    (rf"(?i)^{_NUM_PREFIX}(r[ée]sultats?)\s*$", "## RESULTS"),
    (rf"(?i)^{_NUM_PREFIX}(r[ée]f[ée]rences?|bibliographie)\s*$", "## REFERENCES"),
    # Spanish
    (rf"(?i)^{_NUM_PREFIX}(resumen)\s*$", "## ABSTRACT"),
    (rf"(?i)^{_NUM_PREFIX}(introducci[oó]n)\s*$", "## INTRODUCTION"),
    (rf"(?i)^{_NUM_PREFIX}(m[eé]todos?|materiales?\s+y\s+m[eé]todos?)\s*$", "## METHODS"),
    (rf"(?i)^{_NUM_PREFIX}(resultados?)\s*$", "## RESULTS"),
    (rf"(?i)^{_NUM_PREFIX}(discusi[oó]n)\s*$", "## DISCUSSION"),
    (rf"(?i)^{_NUM_PREFIX}(conclusi[oó]n|conclusiones)\s*$", "## CONCLUSION"),
    (rf"(?i)^{_NUM_PREFIX}(referencias?|bibliograf[ií]a)\s*$", "## REFERENCES"),
    # Portuguese
    (rf"(?i)^{_NUM_PREFIX}(resumo)\s*$", "## ABSTRACT"),
    (rf"(?i)^{_NUM_PREFIX}(m[eé]todos?|materiais?\s+e\s+m[eé]todos?)\s*$", "## METHODS"),
    (rf"(?i)^{_NUM_PREFIX}(resultados?)\s*$", "## RESULTS"),
    (rf"(?i)^{_NUM_PREFIX}(refer[eê]ncias?)\s*$", "## REFERENCES"),
]

_SECTION_PATTERNS: list[tuple[str, str]] = _EN_PATTERNS + _CJK_PATTERNS + _EU_PATTERNS

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
