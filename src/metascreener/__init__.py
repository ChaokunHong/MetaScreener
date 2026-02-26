"""MetaScreener 2.0 — AI-assisted systematic review tool.

Multi-LLM ensemble for literature screening, data extraction,
and risk of bias assessment. Targeting The Lancet Digital Health.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("metascreener")
except PackageNotFoundError:
    # Fallback for source-only usage before installation.
    __version__ = "2.0.0a4"
__author__ = "Chaokun Hong"
__license__ = "Apache-2.0"
