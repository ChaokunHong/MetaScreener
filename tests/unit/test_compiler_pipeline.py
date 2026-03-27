"""Tests for the full template compilation pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from metascreener.core.enums import FieldRole, SheetCardinality, SheetRole
from metascreener.core.models_extraction import ExtractionSchema
from metascreener.module2_extraction.compiler.compiler import compile_template


class TestCompileTemplate:
    @pytest.mark.asyncio
    async def test_compile_produces_valid_schema(
        self, sample_extraction_template: Path,
    ) -> None:
        mock_backend = AsyncMock()
        mock_backend.generate.side_effect = [
            '{"fields": ['
            '{"name": "Row_ID", "role": "auto_calc", "description": "Auto ID", "required": false},'
            '{"name": "Study_ID", "role": "auto_calc", "description": "Auto ID", "required": false},'
            '{"name": "First_Author", "role": "extract", "description": "Author", "required": true},'
            '{"name": "Publication_Year", "role": "extract", "description": "Year", "required": true},'
            '{"name": "Study_Design", "role": "extract", "description": "Design", "required": true},'
            '{"name": "Country", "role": "extract", "description": "Country", "required": true},'
            '{"name": "N_Participants", "role": "extract", "description": "Sample size", "required": true},'
            '{"name": "Age_Mean", "role": "extract", "description": "Mean age", "required": false},'
            '{"name": "Female_Percent", "role": "extract", "description": "% female", "required": false},'
            '{"name": "Notes", "role": "metadata", "description": "Notes", "required": false}'
            '], "cardinality": "one_per_study"}',
            '{"fields": ['
            '{"name": "Row_ID", "role": "extract", "description": "FK to study", "required": true},'
            '{"name": "Study_ID_Display", "role": "auto_calc", "description": "Auto", "required": false},'
            '{"name": "Pathogen_Species", "role": "extract", "description": "Pathogen", "required": true},'
            '{"name": "Antibiotic", "role": "extract", "description": "Drug tested", "required": true},'
            '{"name": "Antibiotic_Class", "role": "lookup", "description": "Drug class", "required": false},'
            '{"name": "N_Tested", "role": "extract", "description": "Tested count", "required": true},'
            '{"name": "N_Resistant", "role": "extract", "description": "Resistant count", "required": true},'
            '{"name": "Prevalence_Percent", "role": "auto_calc", "description": "Auto calc", "required": false}'
            '], "cardinality": "many_per_study"}',
        ]

        schema = await compile_template(
            sample_extraction_template, llm_backend=mock_backend,
        )
        assert isinstance(schema, ExtractionSchema)
        assert schema.schema_id is not None
        assert schema.schema_version == "1.0"

    @pytest.mark.asyncio
    async def test_data_sheets_ordered(
        self, sample_extraction_template: Path,
    ) -> None:
        mock_backend = AsyncMock()
        mock_backend.generate.side_effect = [
            '{"fields": [{"name": "Row_ID", "role": "auto_calc", "description": "ID", "required": false}], "cardinality": "one_per_study"}',
            '{"fields": [{"name": "Row_ID", "role": "extract", "description": "FK", "required": true}], "cardinality": "many_per_study"}',
        ]
        schema = await compile_template(
            sample_extraction_template, llm_backend=mock_backend,
        )
        data_sheets = schema.data_sheets
        assert len(data_sheets) >= 2
        names = [s.sheet_name for s in data_sheets]
        assert names.index("Study_Characteristics") < names.index("Resistance_Data")

    @pytest.mark.asyncio
    async def test_mapping_table_extracted(
        self, sample_extraction_template: Path,
    ) -> None:
        mock_backend = AsyncMock()
        mock_backend.generate.side_effect = [
            '{"fields": [{"name": "Row_ID", "role": "auto_calc", "description": "ID", "required": false}], "cardinality": "one_per_study"}',
            '{"fields": [{"name": "Row_ID", "role": "extract", "description": "FK", "required": true}], "cardinality": "many_per_study"}',
        ]
        schema = await compile_template(
            sample_extraction_template, llm_backend=mock_backend,
        )
        assert "Antibiotic_Mappings" in schema.mappings
        m = schema.mappings["Antibiotic_Mappings"]
        assert m.source_column == "Antibiotic"
        assert "Drug_Class" in m.target_columns
        result = m.lookup("Ampicillin")
        assert result is not None
        assert result["Drug_Class"] == "Penicillins"

    @pytest.mark.asyncio
    async def test_relationships_detected(
        self, sample_extraction_template: Path,
    ) -> None:
        mock_backend = AsyncMock()
        mock_backend.generate.side_effect = [
            '{"fields": [{"name": "Row_ID", "role": "auto_calc", "description": "ID", "required": false}], "cardinality": "one_per_study"}',
            '{"fields": [{"name": "Row_ID", "role": "extract", "description": "FK", "required": true}], "cardinality": "many_per_study"}',
        ]
        schema = await compile_template(
            sample_extraction_template, llm_backend=mock_backend,
        )
        assert len(schema.relationships) >= 1
        rel = schema.relationships[0]
        assert rel.parent_sheet == "Study_Characteristics"
        assert rel.child_sheet == "Resistance_Data"

    @pytest.mark.asyncio
    async def test_schema_json_serializable(
        self, sample_extraction_template: Path,
    ) -> None:
        mock_backend = AsyncMock()
        mock_backend.generate.side_effect = [
            '{"fields": [{"name": "Row_ID", "role": "auto_calc", "description": "ID", "required": false}], "cardinality": "one_per_study"}',
            '{"fields": [{"name": "Row_ID", "role": "extract", "description": "FK", "required": true}], "cardinality": "many_per_study"}',
        ]
        schema = await compile_template(
            sample_extraction_template, llm_backend=mock_backend,
        )
        json_str = schema.model_dump_json()
        restored = ExtractionSchema.model_validate_json(json_str)
        assert restored.schema_id == schema.schema_id

    @pytest.mark.asyncio
    async def test_compile_without_llm(
        self, sample_extraction_template: Path,
    ) -> None:
        schema = await compile_template(
            sample_extraction_template, llm_backend=None,
        )
        assert isinstance(schema, ExtractionSchema)
        data_sheets = schema.data_sheets
        assert len(data_sheets) >= 1

    def test_compile_nonexistent_file(self) -> None:
        import asyncio
        with pytest.raises(FileNotFoundError):
            asyncio.run(compile_template(Path("/nonexistent.xlsx")))
