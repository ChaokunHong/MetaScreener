"""RoB tool schema registry and auto-selection."""
from __future__ import annotations

from metascreener.core.enums import StudyType
from metascreener.module3_quality.tools.base import RoBToolSchema
from metascreener.module3_quality.tools.quadas2 import QUADAS2Schema
from metascreener.module3_quality.tools.rob2 import RoB2Schema
from metascreener.module3_quality.tools.robins_i import ROBINSISchema

_REGISTRY: dict[str, type[RoBToolSchema]] = {
    "rob2": RoB2Schema,
    "robins_i": ROBINSISchema,
    "quadas2": QUADAS2Schema,
}

_STUDY_TYPE_MAP: dict[StudyType, str] = {
    StudyType.RCT: "rob2",
    StudyType.OBSERVATIONAL: "robins_i",
    StudyType.DIAGNOSTIC: "quadas2",
}


def get_tool_schema(tool_name: str) -> RoBToolSchema:
    """Get a tool schema instance by name.

    Args:
        tool_name: One of 'rob2', 'robins_i', 'quadas2'.

    Returns:
        Instantiated tool schema.

    Raises:
        ValueError: If tool_name is not recognized.
    """
    cls = _REGISTRY.get(tool_name)
    if cls is None:
        raise ValueError(
            f"Unknown RoB tool: '{tool_name}'. "
            f"Available: {', '.join(_REGISTRY)}"
        )
    return cls()


def get_tool_for_study_type(study_type: StudyType) -> RoBToolSchema:
    """Auto-select the appropriate RoB tool based on study type.

    Args:
        study_type: The study design classification.

    Returns:
        Instantiated tool schema for the given study type.

    Raises:
        ValueError: If no tool is mapped for this study type.
    """
    tool_name = _STUDY_TYPE_MAP.get(study_type)
    if tool_name is None:
        raise ValueError(
            f"No RoB tool mapped for study type '{study_type.value}'. "
            f"Supported: {', '.join(st.value for st in _STUDY_TYPE_MAP)}"
        )
    return get_tool_schema(tool_name)
