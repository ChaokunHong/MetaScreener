"""Streamlit page for literature screening.

Provides a full screening UI with multi-format file upload, criteria loading,
record preview, and HCN screening execution with results visualization.
"""
# ruff: noqa: N999
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from metascreener.core.enums import Decision, Tier
from metascreener.core.models import Record, ReviewCriteria, ScreeningDecision
from metascreener.criteria.schema import CriteriaSchema
from metascreener.io.readers import read_records

if TYPE_CHECKING:
    from streamlit.runtime.uploaded_file_manager import UploadedFile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_RECORD_UPLOAD_EXTENSIONS = ["ris", "bib", "csv", "xlsx", "json"]
_CRITERIA_UPLOAD_EXTENSIONS = ["yaml", "yml"]
_ABSTRACT_PREVIEW_LEN = 200

# Tier display labels
_TIER_LABELS: dict[int, str] = {
    Tier.ZERO: "Tier 0 (Rule Override)",
    Tier.ONE: "Tier 1 (Unanimous)",
    Tier.TWO: "Tier 2 (Majority)",
    Tier.THREE: "Tier 3 (Human Review)",
}

# Decision badge colours for Plotly
_DECISION_COLORS: dict[str, str] = {
    Decision.INCLUDE: "#2ecc71",
    Decision.EXCLUDE: "#e74c3c",
    Decision.HUMAN_REVIEW: "#f39c12",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _save_uploaded_to_temp(uploaded_file: UploadedFile) -> Path:
    """Write an uploaded Streamlit file to a temporary file on disk.

    Args:
        uploaded_file: Streamlit UploadedFile object.

    Returns:
        Path to the temporary file.
    """
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        return Path(tmp.name)


def _load_records_from_upload(uploaded_file: UploadedFile) -> list[Record]:
    """Parse uploaded records using the IO reader or JSON fallback.

    For .json files (not supported by the IO reader), records are parsed
    manually. All other formats are written to a temp file and passed to
    ``read_records``.

    Args:
        uploaded_file: Streamlit UploadedFile object.

    Returns:
        List of parsed Record objects.
    """
    name = uploaded_file.name
    if name.endswith(".json"):
        return _load_records_from_json(uploaded_file)

    tmp_path = _save_uploaded_to_temp(uploaded_file)
    try:
        return read_records(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _load_records_from_json(uploaded_file: UploadedFile) -> list[Record]:
    """Parse records from a JSON file upload.

    Expects a JSON array of objects with at least a ``title`` field.

    Args:
        uploaded_file: Streamlit UploadedFile with .json extension.

    Returns:
        List of Record objects.
    """
    raw_bytes = uploaded_file.getvalue()
    data = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(data, list):
        data = [data]

    records: list[Record] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "").strip()
        if not title:
            continue
        kwargs: dict[str, Any] = {"title": title}
        if "abstract" in item:
            kwargs["abstract"] = item["abstract"]
        if "authors" in item:
            authors = item["authors"]
            kwargs["authors"] = authors if isinstance(authors, list) else [str(authors)]
        if "year" in item:
            try:
                kwargs["year"] = int(item["year"])
            except (ValueError, TypeError):
                pass
        if "record_id" in item:
            kwargs["record_id"] = str(item["record_id"])
        if "doi" in item:
            kwargs["doi"] = item["doi"]
        if "journal" in item:
            kwargs["journal"] = item["journal"]
        records.append(Record(**kwargs))
    return records


def _load_criteria_from_upload(uploaded_file: UploadedFile) -> ReviewCriteria:
    """Parse uploaded criteria YAML via CriteriaSchema.

    Args:
        uploaded_file: Streamlit UploadedFile with .yaml/.yml extension.

    Returns:
        Parsed ReviewCriteria object.
    """
    tmp_path = _save_uploaded_to_temp(uploaded_file)
    try:
        return CriteriaSchema.load(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _records_to_preview_df(records: list[Record]) -> pd.DataFrame:
    """Convert records to a preview DataFrame with truncated abstracts.

    Args:
        records: List of Record objects.

    Returns:
        DataFrame with columns for preview display.
    """
    rows: list[dict[str, Any]] = []
    for rec in records:
        abstract_text = rec.abstract or ""
        truncated = (
            abstract_text[:_ABSTRACT_PREVIEW_LEN] + "..."
            if len(abstract_text) > _ABSTRACT_PREVIEW_LEN
            else abstract_text
        )
        authors_str = "; ".join(rec.authors[:3])
        if len(rec.authors) > 3:
            authors_str += f" (+{len(rec.authors) - 3} more)"

        rows.append({
            "record_id": rec.record_id[:12] + "...",
            "title": rec.title,
            "authors": authors_str,
            "year": rec.year,
            "abstract": truncated,
        })
    return pd.DataFrame(rows)


def _results_to_df(results: list[ScreeningDecision]) -> pd.DataFrame:
    """Convert screening results to a display DataFrame.

    Args:
        results: List of ScreeningDecision objects.

    Returns:
        DataFrame with decision details.
    """
    rows: list[dict[str, Any]] = []
    for res in results:
        rows.append({
            "record_id": res.record_id[:12] + "...",
            "decision": res.decision.value,
            "tier": _TIER_LABELS.get(res.tier, str(res.tier)),
            "score": round(res.final_score, 4),
            "confidence": round(res.ensemble_confidence, 4),
            "n_models": len(res.model_outputs),
        })
    return pd.DataFrame(rows)


def _results_to_export_csv(results: list[ScreeningDecision]) -> str:
    """Serialize screening results as CSV text.

    Args:
        results: List of ScreeningDecision objects.

    Returns:
        CSV string.
    """
    rows: list[dict[str, Any]] = []
    for res in results:
        rows.append({
            "record_id": res.record_id,
            "decision": res.decision.value,
            "tier": res.tier.value,
            "final_score": round(res.final_score, 4),
            "ensemble_confidence": round(res.ensemble_confidence, 4),
            "n_models": len(res.model_outputs),
        })
    csv_output: str = pd.DataFrame(rows).to_csv(index=False)
    return csv_output


def _results_to_export_json(results: list[ScreeningDecision]) -> str:
    """Serialize screening results as JSON text.

    Args:
        results: List of ScreeningDecision objects.

    Returns:
        JSON string.
    """
    items: list[dict[str, Any]] = []
    for res in results:
        items.append({
            "record_id": res.record_id,
            "decision": res.decision.value,
            "tier": res.tier.value,
            "final_score": round(res.final_score, 4),
            "ensemble_confidence": round(res.ensemble_confidence, 4),
            "n_models": len(res.model_outputs),
        })
    return json.dumps(items, indent=2)


def _build_decision_pie(results: list[ScreeningDecision]) -> go.Figure:
    """Build a Plotly pie chart of decision distribution.

    Args:
        results: List of ScreeningDecision objects.

    Returns:
        Plotly Figure.
    """
    counts: dict[str, int] = {d.value: 0 for d in Decision}
    for res in results:
        counts[res.decision.value] += 1

    labels = list(counts.keys())
    values = list(counts.values())
    colors = [_DECISION_COLORS.get(label, "#95a5a6") for label in labels]

    fig = px.pie(
        names=labels,
        values=values,
        color_discrete_sequence=colors,
        title="Decision Distribution",
    )
    fig.update_traces(textinfo="label+percent+value")
    fig.update_layout(margin={"t": 40, "b": 10, "l": 10, "r": 10})
    return fig


async def _run_screening(
    records: list[Record],
    criteria: ReviewCriteria,
    seed: int,
    progress_bar: st.delta_generator.DeltaGenerator,
    status_text: st.delta_generator.DeltaGenerator,
) -> list[ScreeningDecision]:
    """Execute HCN screening on records asynchronously.

    Sets up OpenRouter backends from environment and runs TAScreener
    batch screening with progress updates.

    Args:
        records: Records to screen.
        criteria: Review criteria.
        seed: Random seed.
        progress_bar: Streamlit progress bar widget.
        status_text: Streamlit text widget for status updates.

    Returns:
        List of ScreeningDecision objects.
    """
    from metascreener.llm.adapters.openrouter import OpenRouterAdapter  # noqa: PLC0415
    from metascreener.module1_screening.ta_screener import TAScreener  # noqa: PLC0415

    api_key = os.environ.get("OPENROUTER_API_KEY", "")

    # Set up backends -- use a subset of models for interactive screening
    backends = [
        OpenRouterAdapter(
            model_id="qwen3",
            openrouter_model_name="qwen/qwen3-235b-a22b",
            api_key=api_key,
            model_version="2025-04-28",
        ),
        OpenRouterAdapter(
            model_id="deepseek-v3",
            openrouter_model_name="deepseek/deepseek-chat",
            api_key=api_key,
            model_version="2025-03-24",
        ),
    ]

    screener = TAScreener(backends=backends)
    results: list[ScreeningDecision] = []
    total = len(records)

    for i, record in enumerate(records):
        status_text.text(f"Screening record {i + 1}/{total}: {record.title[:60]}...")
        progress_bar.progress((i + 1) / total)
        result = await screener.screen_single(record, criteria, seed=seed)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------


def main() -> None:
    """Render the screening page with upload, preview, execution, and results."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Screening",
        page_icon="\U0001f50d",
        layout="wide",
    )
    st.title("Literature Screening")
    st.markdown(
        "Screen papers using the **Hierarchical Consensus Network** (HCN). "
        "Upload your search results and review criteria to get started."
    )

    # ------------------------------------------------------------------
    # Sidebar: File uploads and controls
    # ------------------------------------------------------------------
    with st.sidebar:
        st.header("Input Files")

        uploaded_records_file = st.file_uploader(
            "Upload records",
            type=_RECORD_UPLOAD_EXTENSIONS,
            help="Supported formats: RIS, BibTeX, CSV, Excel (.xlsx), JSON",
        )

        criteria_file = st.file_uploader(
            "Upload criteria (YAML)",
            type=_CRITERIA_UPLOAD_EXTENSIONS,
            help="Structured review criteria file (criteria.yaml)",
        )

        st.markdown("---")
        st.header("Screening Settings")

        stage = st.selectbox(
            "Screening stage",
            options=["Title/Abstract", "Full Text"],
            index=0,
            help="Title/Abstract screening uses titles and abstracts only. "
            "Full-text screening requires PDF files.",
        )

        seed = st.number_input(
            "Random seed",
            value=42,
            min_value=0,
            help="Seed for reproducible screening results.",
        )

        # API key status
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        st.markdown("---")
        st.header("API Status")
        if api_key:
            st.success("OPENROUTER_API_KEY configured")
        else:
            st.warning("OPENROUTER_API_KEY not set")
            st.caption(
                "Set this environment variable to enable LLM-based screening."
            )

    # ------------------------------------------------------------------
    # Load records
    # ------------------------------------------------------------------
    records: list[Record] = []
    if uploaded_records_file is not None:
        try:
            records = _load_records_from_upload(uploaded_records_file)
            st.session_state["screening_records"] = records
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to parse records file: {exc}")
    elif "screening_records" in st.session_state:
        records = st.session_state["screening_records"]

    # ------------------------------------------------------------------
    # Load criteria
    # ------------------------------------------------------------------
    criteria: ReviewCriteria | None = None
    if criteria_file is not None:
        try:
            criteria = _load_criteria_from_upload(criteria_file)
            st.session_state["screening_criteria"] = criteria
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to parse criteria file: {exc}")
    elif "screening_criteria" in st.session_state:
        criteria = st.session_state["screening_criteria"]

    # ------------------------------------------------------------------
    # Record preview
    # ------------------------------------------------------------------
    if records:
        st.subheader("Records Preview")

        # Stats row
        total_count = len(records)
        with_abstract = sum(1 for r in records if r.abstract)
        without_abstract = total_count - with_abstract

        col_total, col_with, col_without = st.columns(3)
        col_total.metric("Total Records", total_count)
        col_with.metric("With Abstract", with_abstract)
        col_without.metric("Without Abstract", without_abstract)

        if without_abstract > 0:
            st.info(
                f"{without_abstract} record(s) have no abstract. "
                "Records without abstracts will default to INCLUDE "
                "(maximizing recall per TRIPOD-LLM Item 13)."
            )

        # Searchable preview table
        preview_df = _records_to_preview_df(records)
        st.dataframe(
            preview_df,
            use_container_width=True,
            height=min(400, 35 * len(preview_df) + 38),
            column_config={
                "record_id": st.column_config.TextColumn("ID", width="small"),
                "title": st.column_config.TextColumn("Title", width="large"),
                "authors": st.column_config.TextColumn("Authors", width="medium"),
                "year": st.column_config.NumberColumn("Year", format="%d"),
                "abstract": st.column_config.TextColumn(
                    "Abstract (truncated)", width="large"
                ),
            },
        )
    else:
        st.info(
            "Upload records in the sidebar to begin screening. "
            "Supported formats: RIS, BibTeX, CSV, Excel, JSON."
        )

    # ------------------------------------------------------------------
    # Criteria preview
    # ------------------------------------------------------------------
    if criteria is not None:
        with st.expander("Loaded Criteria", expanded=False):
            st.markdown(f"**Framework:** {criteria.framework.value.upper()}")
            if criteria.research_question:
                st.markdown(f"**Research Question:** {criteria.research_question}")
            for _key, element in criteria.elements.items():
                st.markdown(f"**{element.name}**")
                if element.include:
                    st.markdown(f"  - Include: {', '.join(element.include)}")
                if element.exclude:
                    st.markdown(f"  - Exclude: {', '.join(element.exclude)}")

    # ------------------------------------------------------------------
    # Run screening
    # ------------------------------------------------------------------
    st.markdown("---")

    can_run = bool(records) and criteria is not None
    run_disabled = not can_run

    if not records:
        st.warning("Upload records to enable screening.")
    elif criteria is None:
        st.warning("Upload review criteria (YAML) to enable screening.")

    if st.button("Run Screening", type="primary", disabled=run_disabled):
        if not api_key:
            st.warning(
                "**OPENROUTER_API_KEY is not configured.** "
                "Set this environment variable before running screening.\n\n"
                "```bash\n"
                "export OPENROUTER_API_KEY='your-key-here'\n"
                "```\n\n"
                "You can obtain an API key from [OpenRouter](https://openrouter.ai/)."
            )
        elif stage == "Full Text":
            st.warning(
                "Full-text screening requires PDF files and is not yet "
                "supported in the web UI. Use the CLI: "
                "`metascreener screen --stage ft`"
            )
        else:
            assert criteria is not None  # type guard
            with st.status("Screening in progress...", expanded=True) as status:
                progress_bar = st.progress(0)
                status_text = st.empty()
                status_text.text("Initializing screening pipeline...")

                try:
                    results = asyncio.run(
                        _run_screening(
                            records=records,
                            criteria=criteria,
                            seed=int(seed),
                            progress_bar=progress_bar,
                            status_text=status_text,
                        )
                    )
                    st.session_state["screening_results"] = results
                    status.update(
                        label="Screening complete!", state="complete", expanded=False
                    )
                    st.success(
                        f"Screened {len(results)} records successfully."
                    )
                except Exception as exc:  # noqa: BLE001
                    status.update(label="Screening failed", state="error")
                    st.error(f"Screening failed: {exc}")

    # ------------------------------------------------------------------
    # Results display
    # ------------------------------------------------------------------
    if "screening_results" in st.session_state:
        stored_results: list[ScreeningDecision] = st.session_state[
            "screening_results"
        ]
        st.markdown("---")
        st.subheader("Screening Results")

        # Summary metrics
        n_total = len(stored_results)
        n_include = sum(
            1 for r in stored_results if r.decision == Decision.INCLUDE
        )
        n_exclude = sum(
            1 for r in stored_results if r.decision == Decision.EXCLUDE
        )
        n_review = sum(
            1 for r in stored_results if r.decision == Decision.HUMAN_REVIEW
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Screened", n_total)
        m2.metric("Included", n_include)
        m3.metric("Excluded", n_exclude)
        m4.metric("Human Review", n_review)

        # Results table and chart side by side
        col_table, col_chart = st.columns([3, 2])

        with col_table:
            st.markdown("#### Decision Table")
            results_df = _results_to_df(stored_results)
            st.dataframe(
                results_df,
                use_container_width=True,
                height=min(400, 35 * len(results_df) + 38),
                column_config={
                    "record_id": st.column_config.TextColumn(
                        "ID", width="small"
                    ),
                    "decision": st.column_config.TextColumn("Decision"),
                    "tier": st.column_config.TextColumn("Tier"),
                    "score": st.column_config.NumberColumn(
                        "Score", format="%.4f"
                    ),
                    "confidence": st.column_config.NumberColumn(
                        "Confidence", format="%.4f"
                    ),
                    "n_models": st.column_config.NumberColumn("Models"),
                },
            )

        with col_chart:
            st.markdown("#### Decision Distribution")
            fig = _build_decision_pie(stored_results)
            st.plotly_chart(fig, use_container_width=True)

        # Export buttons
        st.markdown("#### Export Results")
        exp_col1, exp_col2, _ = st.columns([1, 1, 3])
        with exp_col1:
            csv_data = _results_to_export_csv(stored_results)
            st.download_button(
                "Download CSV",
                data=csv_data,
                file_name="screening_results.csv",
                mime="text/csv",
            )
        with exp_col2:
            json_data = _results_to_export_json(stored_results)
            st.download_button(
                "Download JSON",
                data=json_data,
                file_name="screening_results.json",
                mime="application/json",
            )


if __name__ == "__main__":
    main()
