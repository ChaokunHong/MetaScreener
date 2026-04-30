"""Export sub-package for module2_extraction.

Provides exporters for Excel, CSV, RevMan XML, R metafor, and
template-filling formats.
"""
from metascreener.module2_extraction.export.csv_export import export_to_csv
from metascreener.module2_extraction.export.effect_size_mapper import (
    ContinuousData,
    DichotomousData,
    EffectSizeMapper,
)
from metascreener.module2_extraction.export.excel import export_extraction_results
from metascreener.module2_extraction.export.r_meta import export_to_r_meta
from metascreener.module2_extraction.export.revman import export_to_revman
from metascreener.module2_extraction.export.template_filler import (
    export_filled_template,
)

__all__ = [
    "export_extraction_results",
    "export_filled_template",
    "export_to_csv",
    "export_to_revman",
    "export_to_r_meta",
    "EffectSizeMapper",
    "DichotomousData",
    "ContinuousData",
]
