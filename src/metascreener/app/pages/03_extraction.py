"""Streamlit page for data extraction.

Provides an interactive UI for uploading extraction form YAML and PDFs,
running multi-LLM parallel extraction via ExtractionEngine, and
displaying/exporting structured results with consensus indicators.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import streamlit as st
import yaml

if TYPE_CHECKING:
    from streamlit.runtime.uploaded_file_manager import UploadedFile


def _parse_form_yaml(content: str) -> dict[str, Any] | None:
    """Parse extraction form YAML content safely.

    Args:
        content: Raw YAML string from the uploaded file.

    Returns:
        Parsed dictionary, or None on parse failure.
    """
    try:
        data: dict[str, Any] = yaml.safe_load(content)
        return data
    except yaml.YAMLError as exc:  # noqa: BLE001
        st.error(f"Failed to parse YAML: {exc}")
        return None


def _render_form_table(form_data: dict[str, Any]) -> None:
    """Render the extraction form fields as a structured table.

    Displays form metadata (name, version) and a DataFrame of field
    definitions with columns: Field, Type, Description, Required.

    Args:
        form_data: Parsed YAML dictionary with ``fields`` key.
    """
    form_name = form_data.get("form_name", "Untitled")
    form_version = form_data.get("form_version", "N/A")
    st.markdown(f"**Form:** {form_name}  |  **Version:** {form_version}")

    fields = form_data.get("fields", {})
    if not fields:
        st.warning("No fields defined in the extraction form.")
        return

    rows: list[dict[str, str]] = []
    for field_name, field_def in fields.items():
        if isinstance(field_def, dict):
            rows.append({
                "Field": field_name,
                "Type": str(field_def.get("type", "text")),
                "Description": str(field_def.get("description", "")),
                "Required": "Yes" if field_def.get("required", False) else "No",
            })
        else:
            rows.append({
                "Field": field_name,
                "Type": "unknown",
                "Description": str(field_def),
                "Required": "No",
            })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_pdf_table(pdf_files: list[UploadedFile]) -> None:
    """Render uploaded PDFs as a table with file name and size.

    Args:
        pdf_files: List of Streamlit UploadedFile objects.
    """
    rows: list[dict[str, str]] = []
    for pdf in pdf_files:
        size_bytes = pdf.size
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        rows.append({"File Name": pdf.name, "Size": size_str})

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _save_pdf_to_temp(pdf_file: UploadedFile) -> Path:
    """Write an uploaded PDF to a temporary file and return its path.

    Args:
        pdf_file: Streamlit UploadedFile for a PDF.

    Returns:
        Path to the temporary file.
    """
    suffix = Path(pdf_file.name).suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(pdf_file.read())
    tmp.close()
    pdf_file.seek(0)  # Reset for potential re-read
    return Path(tmp.name)


def _run_extraction(
    form_content: str,
    pdf_files: list[UploadedFile],
    seed: int,
) -> list[dict[str, Any]]:
    """Execute data extraction across all PDFs using ExtractionEngine.

    Creates OpenRouter backends from the environment API key, loads the
    extraction form, extracts text from each PDF, and runs extraction.

    Args:
        form_content: Raw YAML string for the extraction form.
        pdf_files: List of Streamlit UploadedFile objects for PDFs.
        seed: Reproducibility seed.

    Returns:
        List of per-paper result dictionaries suitable for DataFrame display.

    Raises:
        RuntimeError: If extraction fails for all papers.
    """
    from metascreener.io.pdf_parser import extract_text_from_pdf  # noqa: PLC0415
    from metascreener.module2_extraction.extractor import ExtractionEngine  # noqa: PLC0415
    from metascreener.module2_extraction.form_schema import ExtractionForm  # noqa: PLC0415

    # Load form from YAML content
    form_data = yaml.safe_load(form_content)
    form = ExtractionForm(**form_data)

    # Set up backends
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    from metascreener.config import load_model_config  # noqa: PLC0415
    from metascreener.llm.adapters.openrouter import OpenRouterAdapter  # noqa: PLC0415

    config_path = Path(__file__).resolve().parents[2] / "configs" / "models.yaml"
    if not config_path.exists():
        # Fallback: try project root (developer mode)
        config_path = Path.cwd() / "configs" / "models.yaml"

    config = load_model_config(config_path)
    backends = []
    for name, entry in config.models.items():
        adapter = OpenRouterAdapter(
            model_id=name,
            openrouter_model_name=entry.model_id,
            api_key=api_key,
            model_version=entry.version,
            timeout_s=config.inference.timeout_s,
            max_retries=config.inference.max_retries,
        )
        backends.append(adapter)

    engine = ExtractionEngine(backends=backends)

    # Process each PDF
    all_results: list[dict[str, Any]] = []

    async def _run_all() -> list[dict[str, Any]]:
        """Run extraction for all PDFs asynchronously."""
        results: list[dict[str, Any]] = []
        for pdf_file in pdf_files:
            tmp_path = _save_pdf_to_temp(pdf_file)
            try:
                text = extract_text_from_pdf(tmp_path)
                if not text.strip():
                    st.warning(f"No text extracted from {pdf_file.name} (image-only PDF?).")
                    continue

                result = await engine.extract(text=text, form=form, seed=seed)
                result_dict = result.extracted_fields.copy()
                result_dict["_paper"] = pdf_file.name
                result_dict["_consensus_count"] = len(result.consensus_fields)
                result_dict["_discrepant_count"] = len(result.discrepant_fields)
                result_dict["_needs_review"] = result.requires_human_review
                results.append(result_dict)
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Extraction failed for {pdf_file.name}: {exc}")
            finally:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        return results

    loop = asyncio.new_event_loop()
    try:
        all_results = loop.run_until_complete(_run_all())
    finally:
        loop.close()

    return all_results


def _build_consensus_df(results: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame showing per-field consensus indicators.

    Args:
        results: List of per-paper result dicts from extraction.

    Returns:
        DataFrame with paper name and consensus/discrepancy columns.
    """
    rows: list[dict[str, Any]] = []
    for r in results:
        rows.append({
            "Paper": r.get("_paper", "unknown"),
            "Fields with consensus": r.get("_consensus_count", 0),
            "Discrepant fields": r.get("_discrepant_count", 0),
            "Needs review": r.get("_needs_review", False),
        })
    return pd.DataFrame(rows)


def _build_extraction_df(results: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a clean extraction DataFrame excluding internal metadata columns.

    Args:
        results: List of per-paper result dicts from extraction.

    Returns:
        DataFrame with Paper column and all extracted field columns.
    """
    clean_rows: list[dict[str, Any]] = []
    for r in results:
        row: dict[str, Any] = {"Paper": r.get("_paper", "unknown")}
        for k, v in r.items():
            if not k.startswith("_"):
                row[k] = v
        clean_rows.append(row)
    return pd.DataFrame(clean_rows)


def _export_csv(df: pd.DataFrame) -> str:
    """Export a DataFrame to CSV string.

    Args:
        df: DataFrame to export.

    Returns:
        CSV-formatted string.
    """
    buf = StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def _export_json(results: list[dict[str, Any]]) -> str:
    """Export extraction results to JSON string.

    Strips internal metadata keys (prefixed with ``_``) before export.

    Args:
        results: List of per-paper result dicts.

    Returns:
        JSON-formatted string.
    """
    clean: list[dict[str, Any]] = []
    for r in results:
        clean.append({k: v for k, v in r.items() if not k.startswith("_")
                       or k == "_paper"})
    return json.dumps(clean, indent=2, default=str)


def _export_excel(df: pd.DataFrame) -> bytes:
    """Export a DataFrame to Excel bytes.

    Args:
        df: DataFrame to export.

    Returns:
        Excel file content as bytes.
    """
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def main() -> None:
    """Render the data extraction page."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Data Extraction",
        page_icon="\U0001f4cb",
        layout="wide",
    )
    st.title("Data Extraction")
    st.markdown("Extract structured data from included papers using multi-LLM consensus.")

    # --- Sidebar ---
    with st.sidebar:
        st.header("Configuration")
        form_file = st.file_uploader(
            "Extraction form (YAML)",
            type=["yaml", "yml"],
            help="YAML defining fields to extract",
        )
        pdf_files = st.file_uploader(
            "Upload PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            help="PDF files of included papers",
        )
        st.markdown("---")
        seed = st.number_input(
            "Seed",
            value=42,
            min_value=0,
            help="Reproducibility seed for LLM inference",
        )

    # --- Form display ---
    form_content: str | None = None
    form_data: dict[str, Any] | None = None

    if form_file is not None:
        st.subheader("Extraction Form")
        form_content = form_file.read().decode("utf-8")
        form_file.seek(0)  # Reset for potential re-read
        form_data = _parse_form_yaml(form_content)
        if form_data is not None:
            _render_form_table(form_data)
            with st.expander("Raw YAML"):
                st.code(form_content, language="yaml")
    else:
        st.info("Upload an extraction form YAML in the sidebar to get started.")

    st.info(
        "Don't have a form? Use "
        "`metascreener extract init-form --topic 'your topic'` "
        "to generate one."
    )

    # --- PDF file list ---
    if pdf_files:
        st.subheader(f"Uploaded PDFs ({len(pdf_files)})")
        _render_pdf_table(pdf_files)
    elif form_file is not None:
        st.warning("Upload PDF files in the sidebar to extract data from.")

    # --- Extraction controls ---
    st.markdown("---")

    can_run = form_content is not None and form_data is not None and bool(pdf_files)

    if st.button("Run Extraction", type="primary", disabled=not can_run):
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            st.warning(
                "OPENROUTER_API_KEY is not set in your environment. "
                "Set this variable to enable LLM-based extraction. "
                "Example: `export OPENROUTER_API_KEY='sk-...'`"
            )
        elif form_content is not None and pdf_files:
            with st.status("Extracting data...", expanded=True) as status:
                st.write(f"Processing {len(pdf_files)} PDF(s) with seed={seed}...")
                try:
                    results = _run_extraction(
                        form_content=form_content,
                        pdf_files=pdf_files,
                        seed=seed,
                    )
                    if results:
                        st.session_state["extraction_results"] = results
                        status.update(
                            label=f"Extraction complete ({len(results)} papers)",
                            state="complete",
                        )
                    else:
                        status.update(
                            label="No results produced",
                            state="error",
                        )
                        st.error(
                            "Extraction produced no results. "
                            "Check that PDFs contain extractable text."
                        )
                except Exception as exc:  # noqa: BLE001
                    status.update(label="Extraction failed", state="error")
                    st.error(f"Extraction error: {exc}")

    if not can_run and form_file is not None and not pdf_files:
        st.caption("Upload both a form YAML and PDF files to enable extraction.")

    # --- Results display ---
    if "extraction_results" in st.session_state:
        results = st.session_state["extraction_results"]

        st.markdown("---")
        st.subheader("Extraction Results")

        # Consensus summary
        consensus_df = _build_consensus_df(results)
        st.markdown("**Consensus Summary**")
        st.dataframe(consensus_df, use_container_width=True, hide_index=True)

        # Editable extraction data
        st.markdown("**Extracted Data**")
        extraction_df = _build_extraction_df(results)
        edited_df = st.data_editor(
            extraction_df,
            use_container_width=True,
            num_rows="fixed",
            key="extraction_data_editor",
        )

        # Export buttons
        st.markdown("---")
        st.subheader("Export")
        col1, col2, col3 = st.columns(3)

        with col1:
            csv_data = _export_csv(edited_df)
            st.download_button(
                "Download CSV",
                data=csv_data,
                file_name="extracted_data.csv",
                mime="text/csv",
            )

        with col2:
            json_data = _export_json(results)
            st.download_button(
                "Download JSON",
                data=json_data,
                file_name="extracted_data.json",
                mime="application/json",
            )

        with col3:
            excel_data = _export_excel(edited_df)
            st.download_button(
                "Download Excel",
                data=excel_data,
                file_name="extracted_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


if __name__ == "__main__":
    main()
