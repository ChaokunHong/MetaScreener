"""Template Compiler: orchestrates the full Excel -> ExtractionSchema pipeline.

Pipeline:
  1. scan_template()        -> RawSheetInfo list
  2. infer_sheet_roles()    -> role classification
  3. infer_relationships()  -> cross-sheet FKs
  4. enhance_fields()       -> AI field classification (per data sheet)
  5. _extract_mappings()    -> mapping table extraction
  6. _build_schema()        -> assemble ExtractionSchema
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import openpyxl
import structlog

from metascreener.core.enums import FieldRole, SheetCardinality, SheetRole
from metascreener.core.models_extraction import (
    ExtractionSchema,
    FieldSchema,
    MappingTable,
    SheetSchema,
)
from metascreener.module2_extraction.compiler.ai_enhancer import (
    SheetEnhancement,
    _heuristic_enhancement,
    enhance_fields,
)
from metascreener.module2_extraction.compiler.relationships import (
    infer_relationships,
    infer_sheet_roles,
)
from metascreener.module2_extraction.compiler.scanner import (
    RawSheetInfo,
    scan_template,
)

if TYPE_CHECKING:
    from metascreener.llm.base import BaseLLMBackend

log = structlog.get_logger()

# In-memory schema cache keyed by file content hash.
# Avoids redundant compilation when the same template is re-uploaded
# (e.g. session resume, retry after error).
_schema_cache: dict[str, ExtractionSchema] = {}
_CACHE_MAX_SIZE = 32

def _file_hash(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

async def compile_template(
    path: Path,
    *,
    llm_backend: BaseLLMBackend | None = None,
) -> ExtractionSchema:
    """Compile an Excel template into an ExtractionSchema.

    Args:
        path: Path to the Excel template file.
        llm_backend: Optional LLM backend with an async ``generate`` method.
            When None, heuristic field classification is used instead.

    Returns:
        A fully assembled ExtractionSchema.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")

    # Cache check — return cached schema if template content is unchanged
    content_hash = _file_hash(path)
    cached = _schema_cache.get(content_hash)
    if cached is not None:
        log.info("compile_cache_hit", schema_id=cached.schema_id)
        return cached

    # Step 1: Structure scan
    raw_sheets = scan_template(path)
    log.info("compile_step1_done", sheets=len(raw_sheets))

    # Step 2: Role classification
    roles = infer_sheet_roles(raw_sheets)
    log.info("compile_step2_done", roles=roles)

    # Step 3: Relationship inference (data sheets only)
    data_raw = [s for s in raw_sheets if roles.get(s.sheet_name) == "data"]
    relationships = infer_relationships(data_raw)
    log.info("compile_step3_done", relationships=len(relationships))

    # Step 4: AI-enhanced field understanding (data sheets only)
    enhancements: dict[str, SheetEnhancement] = {}
    for sheet in data_raw:
        if llm_backend is not None:
            enhancements[sheet.sheet_name] = await enhance_fields(
                sheet, backend=llm_backend,
            )
        else:
            enhancements[sheet.sheet_name] = _heuristic_enhancement(sheet)
    log.info("compile_step4_done", enhanced_sheets=len(enhancements))

    # Step 5: Extract mapping tables
    mapping_raw = [s for s in raw_sheets if roles.get(s.sheet_name) == "mapping"]
    mappings = _extract_mappings(path, mapping_raw)
    log.info("compile_step5_done", mappings=len(mappings))

    # Step 6: Assemble schema
    schema = _build_schema(raw_sheets, roles, relationships, enhancements, mappings)
    log.info(
        "compile_complete",
        schema_id=schema.schema_id,
        data_sheets=len(schema.data_sheets),
        total_fields=sum(len(s.fields) for s in schema.sheets),
    )

    # Store in cache (evict oldest if full)
    if len(_schema_cache) >= _CACHE_MAX_SIZE:
        oldest_key = next(iter(_schema_cache))
        del _schema_cache[oldest_key]
    _schema_cache[content_hash] = schema

    return schema

def _extract_mappings(
    path: Path,
    mapping_sheets: list[RawSheetInfo],
) -> dict[str, MappingTable]:
    """Extract mapping table contents from Excel.

    Args:
        path: Path to the Excel template.
        mapping_sheets: List of raw sheet info for sheets classified as mapping.

    Returns:
        Dictionary of table name -> MappingTable.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    mappings: dict[str, MappingTable] = {}

    for raw_sheet in mapping_sheets:
        ws = wb[raw_sheet.sheet_name]
        if not raw_sheet.fields:
            continue

        source_col = raw_sheet.fields[0].name
        target_cols = [f.name for f in raw_sheet.fields[1:]]

        entries: dict[str, dict[str, Any]] = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            key = str(row[0])
            entry: dict[str, Any] = {}
            for i, col_name in enumerate(target_cols, start=1):
                if i < len(row):
                    entry[col_name] = row[i]
            entries[key] = entry

        mappings[raw_sheet.sheet_name] = MappingTable(
            table_name=raw_sheet.sheet_name,
            source_column=source_col,
            target_columns=target_cols,
            entries=entries,
        )

    wb.close()
    return mappings

def _build_schema(
    raw_sheets: list[RawSheetInfo],
    roles: dict[str, str],
    relationships: list[Any],
    enhancements: dict[str, SheetEnhancement],
    mappings: dict[str, MappingTable],
) -> ExtractionSchema:
    """Assemble the final ExtractionSchema from all pipeline outputs.

    Args:
        raw_sheets: All sheets from the scanner.
        roles: Sheet name -> role string mapping.
        relationships: Inferred cross-sheet relations.
        enhancements: AI or heuristic field enhancements per data sheet.
        mappings: Extracted mapping tables.

    Returns:
        Fully assembled ExtractionSchema.
    """
    # Determine extraction order: parents come before children
    parent_names = {r.parent_sheet for r in relationships}
    child_names = {r.child_sheet for r in relationships}

    data_sheet_names = [
        s.sheet_name for s in raw_sheets if roles.get(s.sheet_name) == "data"
    ]
    ordered_data: list[str] = []
    # Parents first (sheets that are parents but not children of anything)
    for name in data_sheet_names:
        if name in parent_names and name not in child_names:
            ordered_data.append(name)
    # Then remaining data sheets (children and unrelated)
    for name in data_sheet_names:
        if name not in ordered_data:
            ordered_data.append(name)

    sheets: list[SheetSchema] = []
    for raw_sheet in raw_sheets:
        role_str = roles.get(raw_sheet.sheet_name, "data")
        role = SheetRole(role_str)

        enhancement = enhancements.get(raw_sheet.sheet_name)

        if role == SheetRole.DATA and raw_sheet.sheet_name in ordered_data:
            order = ordered_data.index(raw_sheet.sheet_name) + 1
        else:
            order = 0

        cardinality_str = "one_per_study"
        if enhancement is not None:
            cardinality_str = enhancement.cardinality
        cardinality = SheetCardinality(cardinality_str)

        fields: list[FieldSchema] = []
        for f in raw_sheet.fields:
            if enhancement and f.name in enhancement.fields:
                enh = enhancement.fields[f.name]
                field_role = enh.role
                description = enh.description
                required = enh.required
            else:
                field_role = FieldRole.EXTRACT
                description = f.name.replace("_", " ")
                required = False

            if f.dropdown_options:
                field_type = "dropdown"
            else:
                field_type = f.inferred_type

            # Check if this field is a target column in any mapping table
            mapping_source = None
            for m_name, m_table in mappings.items():
                if f.name in m_table.target_columns:
                    mapping_source = m_name
                    if field_role == FieldRole.EXTRACT:
                        field_role = FieldRole.LOOKUP
                    break

            fields.append(FieldSchema(
                column=f.column_letter,
                name=f.name,
                description=description,
                field_type=field_type,
                role=field_role,
                required=required,
                dropdown_options=f.dropdown_options,
                mapping_source=mapping_source,
            ))

        sheets.append(SheetSchema(
            sheet_name=raw_sheet.sheet_name,
            role=role,
            cardinality=cardinality,
            fields=fields,
            extraction_order=order,
        ))

    return ExtractionSchema(
        schema_id=str(uuid.uuid4())[:8],
        schema_version="1.0",
        sheets=sheets,
        relationships=relationships,
        mappings=mappings,
    )
