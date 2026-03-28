"""FigureReader — VLM_FIGURE extraction strategy.

Extracts values from figures using pre-extracted data stored in
StructuredDocument.figures[*].extracted_data (zero VLM calls).

When pre-extracted data is unavailable, the async ``extract_with_vlm``
method can be called with a VLM backend to perform on-demand extraction.
"""
from __future__ import annotations

import json

import structlog

from metascreener.doc_engine.models import StructuredDocument
from metascreener.module2_extraction.models import (
    ExtractionStrategy,
    RawExtractionResult,
    SourceHint,
    SourceLocation,
)

logger = structlog.get_logger(__name__)

# Confidence assigned when value is read from pre-extracted figure data.
_CONFIDENCE_PRIOR = 0.80


def _make_error_result(msg: str, panel_label: str | None = None) -> RawExtractionResult:
    """Return a failed RawExtractionResult for the VLM_FIGURE strategy."""
    return RawExtractionResult(
        value=None,
        evidence=SourceLocation(
            type="figure",
            page=0,
            panel_label=panel_label,
        ),
        strategy_used=ExtractionStrategy.VLM_FIGURE,
        confidence_prior=0.0,
        model_id=None,
        error=msg,
    )


class FigureReader:
    """Extract values from figures using pre-extracted data.

    This reader operates without any VLM calls by reading the
    ``extracted_data`` dictionaries that are already stored on
    :class:`~metascreener.doc_engine.models.Figure` and
    :class:`~metascreener.doc_engine.models.SubFigure` objects.

    For VLM-assisted extraction (when ``extracted_data`` is absent),
    the caller is responsible for performing the VLM call and storing
    the result back on the figure before delegating to this reader.
    """

    def extract_from_preextracted(
        self,
        doc: StructuredDocument,
        hint: SourceHint,
        field_name: str,
    ) -> RawExtractionResult:
        """Extract a field value from a figure's pre-extracted data.

        Lookup priority:
        1. If ``hint.panel_label`` is set *and* a matching sub-figure with
           non-empty ``extracted_data`` exists, use that sub-figure's data.
        2. Otherwise, use the parent figure's ``extracted_data``.

        Key matching priority within the chosen data dict:
        1. Exact match on ``field_name``.
        2. Case-insensitive match.

        Args:
            doc: The :class:`StructuredDocument` to read from.
            hint: Must supply ``figure_id``; optionally ``panel_label``.
            field_name: The key to look up in the extracted data dict.

        Returns:
            :class:`RawExtractionResult` with the found value, or
            ``value=None`` and a descriptive ``error`` on failure.
        """
        # --- Validate hint ---
        if not hint.figure_id:
            return _make_error_result(
                "SourceHint.figure_id is required for VLM_FIGURE",
                panel_label=hint.panel_label,
            )

        # --- Locate figure ---
        figure = doc.get_figure(hint.figure_id)
        if figure is None:
            logger.debug("figure_not_found", figure_id=hint.figure_id)
            return _make_error_result(
                f"Figure '{hint.figure_id}' not found in document",
                panel_label=hint.panel_label,
            )

        # --- Resolve which extracted_data dict to use ---
        target_data: dict[str, object] | None = None

        if hint.panel_label and figure.sub_figures:
            sub = next(
                (sf for sf in figure.sub_figures if sf.panel_label == hint.panel_label),
                None,
            )
            if sub is not None and sub.extracted_data:
                target_data = sub.extracted_data
                logger.debug(
                    "using_sub_figure_data",
                    figure_id=hint.figure_id,
                    panel_label=hint.panel_label,
                )

        if target_data is None:
            target_data = figure.extracted_data

        if not target_data:
            logger.debug(
                "no_extracted_data",
                figure_id=hint.figure_id,
                panel_label=hint.panel_label,
            )
            return _make_error_result(
                f"No pre-extracted data for {hint.figure_id}",
                panel_label=hint.panel_label,
            )

        # --- Key lookup: exact then case-insensitive ---
        value = target_data.get(field_name)
        if value is None:
            needle = field_name.lower()
            for k, v in target_data.items():
                if k.lower() == needle:
                    value = v
                    break

        if value is None:
            logger.debug(
                "field_not_found",
                figure_id=hint.figure_id,
                field_name=field_name,
            )
            return _make_error_result(
                f"Field '{field_name}' not found in extracted data for {hint.figure_id}",
                panel_label=hint.panel_label,
            )

        location = SourceLocation(
            type="figure",
            page=figure.page,
            figure_id=figure.figure_id,
            panel_label=hint.panel_label,
        )

        logger.debug(
            "figure_field_extracted",
            figure_id=hint.figure_id,
            panel_label=hint.panel_label,
            field_name=field_name,
            value=value,
        )

        return RawExtractionResult(
            value=value,
            evidence=location,
            strategy_used=ExtractionStrategy.VLM_FIGURE,
            confidence_prior=_CONFIDENCE_PRIOR,
            model_id=None,
            error=None,
        )

    async def extract_with_vlm(
        self,
        doc: StructuredDocument,
        hint: SourceHint,
        field_name: str,
        vlm_backend,
    ) -> RawExtractionResult:
        """Extract from figure using VLM when pre-extracted data unavailable.

        Tries pre-extracted data first; only calls the VLM backend when no
        pre-extracted value is available.

        Args:
            doc: The :class:`StructuredDocument` to read from.
            hint: Must supply ``figure_id``; optionally ``panel_label``.
            field_name: The field/key to extract from the figure.
            vlm_backend: An async backend with a ``complete(prompt, seed=int)``
                coroutine that returns the model response string. Should expose
                an optional ``model_id`` attribute.

        Returns:
            :class:`RawExtractionResult` with the extracted value, or
            ``value=None`` and a descriptive ``error`` on failure.
        """
        # 1. Try pre-extracted first
        result = self.extract_from_preextracted(doc, hint, field_name)
        if result.value is not None:
            return result

        # 2. If no pre-extracted data, call VLM
        figure = doc.get_figure(hint.figure_id) if hint.figure_id else None
        if figure is None:
            return _make_error_result(
                f"Figure '{hint.figure_id}' not found",
                panel_label=hint.panel_label,
            )

        if figure.image_path is None or not figure.image_path.exists():
            return _make_error_result(
                f"No image available for {hint.figure_id}",
                panel_label=hint.panel_label,
            )

        # Build extraction prompt
        prompt = (
            f"Extract the value of '{field_name}' from this figure.\n"
            f"Figure caption: {figure.caption}\n"
            f'Return JSON: {{"value": <extracted_value>, "evidence": "description of what you see"}}'
        )

        try:
            response = await vlm_backend.complete(prompt, seed=42)
            data = json.loads(response)
            value = data.get("value")
            evidence_text = data.get("evidence", "")

            logger.debug(
                "vlm_figure_extracted",
                figure_id=hint.figure_id,
                field_name=field_name,
                value=value,
                evidence=evidence_text,
            )

            return RawExtractionResult(
                value=value,
                evidence=SourceLocation(
                    type="figure",
                    page=figure.page,
                    figure_id=figure.figure_id,
                    panel_label=hint.panel_label,
                ),
                strategy_used=ExtractionStrategy.VLM_FIGURE,
                confidence_prior=0.80,
                model_id=getattr(vlm_backend, "model_id", "vlm"),
            )
        except Exception as e:
            logger.warning(
                "vlm_figure_extraction_failed",
                figure_id=hint.figure_id,
                field_name=field_name,
                error=str(e),
            )
            return _make_error_result(
                f"VLM extraction failed: {e}",
                panel_label=hint.panel_label,
            )

    @staticmethod
    def _error(msg: str) -> RawExtractionResult:
        """Convenience alias used in docstring examples."""
        return _make_error_result(msg)
