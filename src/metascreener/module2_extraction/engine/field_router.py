"""FieldRouter — maps schema fields to optimal extraction strategies.

Uses heuristic matching (no LLM calls) to assign each EXTRACT field
one of four strategies:

* DIRECT_TABLE  — field name matches a table column header
* COMPUTED      — field is a computable statistical measure
* VLM_FIGURE    — field references a figure by keyword
* LLM_TEXT      — default fallback with best-matching section hint
"""
from __future__ import annotations

from collections import defaultdict

import structlog

from metascreener.core.enums import FieldRole
from metascreener.core.models_extraction import FieldSchema
from metascreener.doc_engine.models import Figure, StructuredDocument, Table
from metascreener.module2_extraction.engine.routing_helpers import (
    COMPUTABLE_ABBREV as _COMPUTABLE_ABBREV,
)
from metascreener.module2_extraction.engine.routing_helpers import (
    COMPUTABLE_MAP as _COMPUTABLE_MAP,
)
from metascreener.module2_extraction.engine.routing_helpers import (
    FIGURE_KEYWORDS as _FIGURE_KEYWORDS,
)
from metascreener.module2_extraction.engine.routing_helpers import (
    SECTION_KEYWORD_MAP as _SECTION_KEYWORD_MAP,
)
from metascreener.module2_extraction.models import (
    ExtractionPhase,
    ExtractionPlan,
    ExtractionStrategy,
    FieldGroup,
    FieldRoutingPlan,
    SourceHint,
)

log = structlog.get_logger(__name__)

import re as _re

_NORMALISE_RE = _re.compile(r"[^a-z0-9 ]+")

def _normalise_header(text: str) -> str:
    """Lower-case, strip, collapse underscores/hyphens/punctuation to spaces."""
    return _NORMALISE_RE.sub(" ", text.strip().lower().replace("_", " ").replace("-", " ")).strip()

def _match_tier(
    needle: str,
    needle_tokens: set[str],
    header: str,
) -> int:
    """Return match quality tier: 3=exact, 2=token overlap, 1=substring, 0=none."""
    # Tier 3: exact match after normalisation
    if needle == header:
        return 3

    header_tokens = set(header.split())

    # Tier 2: >=50% bidirectional token overlap (handles word reordering)
    if needle_tokens and header_tokens:
        overlap = needle_tokens & header_tokens
        jaccard = len(overlap) / len(needle_tokens | header_tokens)
        if jaccard >= 0.5:
            return 2

    # Tier 1: substring containment — only if shorter side >= 5 chars
    # (avoids false positives like "or" matching "author")
    shorter = min(len(needle), len(header))
    if shorter >= 5 and (needle in header or header in needle):
        return 1

    return 0

class FieldRouter:
    """Route schema fields to optimal extraction strategies.

    All routing is heuristic — no LLM calls are made here.  The router
    is intentionally deterministic so routing plans can be unit-tested.
    """

    def route(
        self,
        fields: list[FieldSchema],
        doc: StructuredDocument,
    ) -> list[FieldRoutingPlan]:
        """Create routing plans for all EXTRACT fields based on document structure.

        Non-EXTRACT fields (METADATA, AUTO_CALC, etc.) are silently skipped.

        Routing priority:
        1. Table column header match → DIRECT_TABLE
        2. Computable measure keyword → COMPUTED
        3. Figure caption keyword match → VLM_FIGURE
        4. Default → LLM_TEXT with best-matching section hint

        Args:
            fields: List of FieldSchema objects from the extraction schema.
            doc: Parsed StructuredDocument to match against.

        Returns:
            List of FieldRoutingPlan, one per EXTRACT field.
        """
        plans: list[FieldRoutingPlan] = []
        for field in fields:
            if field.role != FieldRole.EXTRACT:
                continue
            plan = self._route_single(field, doc)
            log.debug(
                "field_routed",
                field=field.name,
                strategy=plan.strategy,
                confidence=plan.confidence_prior,
            )
            plans.append(plan)
        return plans

    def build_extraction_plan(
        self,
        routing_plans: list[FieldRoutingPlan],
    ) -> ExtractionPlan:
        """Build a phased execution plan from routing plans.

        Phases:
        * Phase 0: DIRECT_TABLE — no dependencies, fastest
        * Phase 1: LLM_TEXT + VLM_FIGURE — may use Phase 0 context
        * Phase 2: COMPUTED — depends on Phase 0 + 1 results

        Phases with no fields are omitted from the output.  An empty
        ``routing_plans`` list produces an ExtractionPlan with no phases.

        Args:
            routing_plans: Pre-computed routing plans from :meth:`route`.

        Returns:
            ExtractionPlan with dependency-ordered phases.
        """
        if not routing_plans:
            return ExtractionPlan(phases=[])

        # Bucket routing plans by phase
        buckets: dict[int, list[FieldRoutingPlan]] = {0: [], 1: [], 2: []}
        for rp in routing_plans:
            if rp.strategy == ExtractionStrategy.DIRECT_TABLE:
                buckets[0].append(rp)
            elif rp.strategy == ExtractionStrategy.COMPUTED:
                buckets[2].append(rp)
            else:  # LLM_TEXT, VLM_FIGURE
                buckets[1].append(rp)

        # Determine which phase IDs actually have fields (for depends_on)
        present_phases = [pid for pid in (0, 1, 2) if buckets[pid]]

        phases: list[ExtractionPhase] = []
        for phase_id in present_phases:
            depends_on = [pid for pid in present_phases if pid < phase_id]

            if phase_id == 0:
                # Phase 0: all table fields in one group
                field_schemas = self._routing_plans_to_field_schemas(buckets[0])
                relevant_tables = list(
                    {rp.source_hint.table_id for rp in buckets[0] if rp.source_hint.table_id}
                )
                field_group = FieldGroup(
                    fields=field_schemas,
                    relevant_sections=[],
                    relevant_tables=relevant_tables,
                    group_type="baseline",
                )
                phases.append(
                    ExtractionPhase(
                        phase_id=phase_id,
                        field_groups=[field_group],
                        depends_on=depends_on,
                    )
                )

            elif phase_id == 1:
                # Phase 1: group LLM_TEXT fields by section for efficient batching;
                # VLM_FIGURE fields each get their own group (different image per field).
                llm_plans = [rp for rp in buckets[1] if rp.strategy == ExtractionStrategy.LLM_TEXT]
                vlm_plans = [rp for rp in buckets[1] if rp.strategy == ExtractionStrategy.VLM_FIGURE]

                groups: list[FieldGroup] = []

                # Group LLM_TEXT fields by their target section
                by_section: defaultdict[str, list[FieldRoutingPlan]] = defaultdict(list)
                for rp in llm_plans:
                    section_key = rp.source_hint.section_name or "__all__"
                    by_section[section_key].append(rp)

                for section_key, section_plans in by_section.items():
                    field_schemas = self._routing_plans_to_field_schemas(section_plans)
                    relevant_sections = (
                        [section_key] if section_key != "__all__" else []
                    )
                    groups.append(
                        FieldGroup(
                            fields=field_schemas,
                            relevant_sections=relevant_sections,
                            relevant_tables=[],
                            group_type="outcome",
                        )
                    )

                # VLM fields — one group per field (different figure/image each)
                for rp in vlm_plans:
                    field_schemas = self._routing_plans_to_field_schemas([rp])
                    groups.append(
                        FieldGroup(
                            fields=field_schemas,
                            relevant_sections=[],
                            relevant_tables=[],
                            group_type="outcome",
                        )
                    )

                if groups:
                    phases.append(
                        ExtractionPhase(
                            phase_id=phase_id,
                            field_groups=groups,
                            depends_on=depends_on,
                        )
                    )

            else:
                # Phase 2: computed fields in one group
                field_schemas = self._routing_plans_to_field_schemas(buckets[2])
                field_group = FieldGroup(
                    fields=field_schemas,
                    relevant_sections=[],
                    relevant_tables=[],
                    group_type="computed",
                )
                phases.append(
                    ExtractionPhase(
                        phase_id=phase_id,
                        field_groups=[field_group],
                        depends_on=depends_on,
                    )
                )

        return ExtractionPlan(phases=phases)

    def _route_single(
        self,
        field: FieldSchema,
        doc: StructuredDocument,
    ) -> FieldRoutingPlan:
        """Route a single EXTRACT field to the best strategy."""
        # 1. Try table match
        table_match = self._find_table_match(field.name, doc)
        if table_match is not None:
            table, col_idx = table_match
            header_value = table.cells[0][col_idx].value
            return FieldRoutingPlan(
                field_name=field.name,
                strategy=ExtractionStrategy.DIRECT_TABLE,
                source_hint=SourceHint(
                    table_id=table.table_id,
                    table_column=header_value,
                ),
                confidence_prior=table.extraction_quality_score,
                fallback_strategy=ExtractionStrategy.LLM_TEXT,
            )

        # 2. Try computed measure
        formula = self._check_computable(field.name)
        if formula is not None:
            return FieldRoutingPlan(
                field_name=field.name,
                strategy=ExtractionStrategy.COMPUTED,
                source_hint=SourceHint(computation_formula=formula),
                confidence_prior=0.90,
                fallback_strategy=None,
            )

        # 3. Try figure match
        figure_match = self._find_figure_match(field.name, doc)
        if figure_match is not None:
            return FieldRoutingPlan(
                field_name=field.name,
                strategy=ExtractionStrategy.VLM_FIGURE,
                source_hint=SourceHint(figure_id=figure_match.figure_id),
                confidence_prior=0.80,
                fallback_strategy=None,
            )

        # 4. Default: LLM_TEXT
        best_section = self._find_best_section(field.name, doc)
        return FieldRoutingPlan(
            field_name=field.name,
            strategy=ExtractionStrategy.LLM_TEXT,
            source_hint=SourceHint(section_name=best_section),
            confidence_prior=0.75,
            fallback_strategy=None,
        )

    def _find_table_match(
        self,
        field_name: str,
        doc: StructuredDocument,
    ) -> tuple[Table, int] | None:
        """Find a table column that best matches *field_name*.

        Uses a multi-tier matching strategy to avoid false positives from
        naive substring matching while still catching reasonable synonyms:

        1. **Exact match** (case-insensitive, after normalisation)
        2. **Token overlap** — >=50% of tokens shared between field name and
           header (handles reordering like "Total N" vs "N Total")
        3. **Substring containment** — only when the shorter string is at
           least 5 chars (avoids "or" matching "author")

        The best match across all tables is returned. Among multiple matches
        the one with the highest tier (most specific) wins; ties broken by
        the table with the highest ``extraction_quality_score``.

        Args:
            field_name: The schema field name to look up.
            doc: Parsed StructuredDocument.

        Returns:
            (Table, column_index) tuple, or None if no match is found.
        """
        needle = _normalise_header(field_name)
        needle_tokens = set(needle.split())

        best: tuple[int, float, Table, int] | None = None  # (tier, quality, table, col)

        for table in doc.tables:
            if not table.cells:
                continue
            header_row = table.cells[0]
            quality = getattr(table, "extraction_quality_score", 0.5)

            for col_idx, cell in enumerate(header_row):
                header = _normalise_header(cell.value)
                if not header:
                    continue

                tier = _match_tier(needle, needle_tokens, header)
                if tier == 0:
                    continue  # no match

                candidate = (tier, quality, table, col_idx)
                if best is None or (tier, quality) > (best[0], best[1]):
                    best = candidate

        if best is not None:
            return best[2], best[3]
        return None

    def _check_computable(self, field_name: str) -> str | None:
        """Return a formula key if *field_name* names a computable measure.

        Multi-word phrases use substring containment.  Short abbreviations
        (``or``, ``rr``, ``md``, ``nnt``) require whole-word matching to
        avoid false positives such as "f**or**est" or "err**or**".

        Args:
            field_name: The schema field name.

        Returns:
            Formula string (e.g. ``"odds_ratio"``), or None.
        """
        import re

        name_lower = field_name.lower().strip()

        # Multi-word phrases: simple substring containment is sufficient
        for keyword, formula in _COMPUTABLE_MAP.items():
            if keyword in name_lower:
                return formula

        # Short abbreviations: whole-word match only
        for abbrev, formula in _COMPUTABLE_ABBREV.items():
            if re.search(rf"\b{re.escape(abbrev)}\b", name_lower):
                return formula

        return None

    def _find_figure_match(
        self,
        field_name: str,
        doc: StructuredDocument,
    ) -> Figure | None:
        """Return a Figure if *field_name* references a figure.

        Triggers when the field name contains figure-related keywords
        (``forest plot``, ``figure``, ``chart``).  Picks the first figure
        whose caption or type aligns with the keyword.

        Args:
            field_name: The schema field name.
            doc: Parsed StructuredDocument.

        Returns:
            Matching Figure, or None.
        """
        name_lower = field_name.lower().strip()
        has_figure_keyword = any(kw in name_lower for kw in _FIGURE_KEYWORDS)
        if not has_figure_keyword or not doc.figures:
            return None

        # Prefer a figure whose caption contains the field name keywords
        for figure in doc.figures:
            caption_lower = figure.caption.lower()
            if any(kw in caption_lower for kw in _FIGURE_KEYWORDS):
                return figure
            if any(word in caption_lower for word in name_lower.split()):
                return figure

        # Fallback: return the first figure if any figure keyword triggered
        return doc.figures[0]

    def _find_best_section(
        self,
        field_name: str,
        doc: StructuredDocument,
    ) -> str | None:
        """Return the most relevant section heading for a text-based field.

        Uses keyword heuristics to map field names to expected sections.
        Falls back to "Results" if available, then the first section, then None.

        Args:
            field_name: The schema field name.
            doc: Parsed StructuredDocument.

        Returns:
            Section heading string, or None if the document has no sections.
        """
        name_lower = field_name.lower()
        existing_headings = {s.heading.lower(): s.heading for s in doc.sections}

        # Check keyword map first
        for keyword, target_section in _SECTION_KEYWORD_MAP.items():
            if keyword in name_lower:
                # Prefer exact heading; fall back to case-insensitive match
                if target_section in existing_headings.values():
                    return target_section
                # Try case-insensitive lookup
                match = existing_headings.get(target_section.lower())
                if match:
                    return match

        # Default: use "Results" if present, else first section heading
        if "results" in existing_headings:
            return existing_headings["results"]
        if doc.sections:
            return doc.sections[0].heading

        return None

    @staticmethod
    def _routing_plans_to_field_schemas(
        plans: list[FieldRoutingPlan],
    ) -> list[FieldSchema]:
        """Reconstruct minimal FieldSchema stubs from routing plans.

        Used only to populate FieldGroup for the ExtractionPlan.  The
        stubs carry only ``name`` (sufficient for downstream grouping).

        Args:
            plans: Routing plans for one phase bucket.

        Returns:
            List of minimal FieldSchema instances.
        """
        from metascreener.core.enums import FieldRole

        return [
            FieldSchema(
                column="",
                name=rp.field_name,
                description="",
                field_type="text",
                role=FieldRole.EXTRACT,
                required=False,
            )
            for rp in plans
        ]
