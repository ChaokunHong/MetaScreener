"""Streamlit page for risk of bias assessment."""
from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from metascreener.core.enums import RoBJudgement
from metascreener.core.models import RoBResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOL_OPTIONS: dict[str, dict[str, str]] = {
    "rob2": {
        "label": "RoB 2 (RCTs)",
        "description": "For randomized controlled trials (5 domains)",
    },
    "robins_i": {
        "label": "ROBINS-I (Observational)",
        "description": "For non-randomized studies (7 domains)",
    },
    "quadas2": {
        "label": "QUADAS-2 (Diagnostic)",
        "description": "For diagnostic accuracy studies (4 domains)",
    },
}

JUDGEMENT_INDICATORS: dict[str, str] = {
    RoBJudgement.LOW: "\U0001f7e2 Low",
    RoBJudgement.SOME_CONCERNS: "\U0001f7e1 Some Concerns",
    RoBJudgement.MODERATE: "\U0001f7e1 Moderate",
    RoBJudgement.HIGH: "\U0001f534 High",
    RoBJudgement.SERIOUS: "\U0001f534 Serious",
    RoBJudgement.CRITICAL: "\u26d4 Critical",
    RoBJudgement.UNCLEAR: "\u2b1c Unclear",
}

DEFAULT_SEED: int = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_file_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable file size string.

    Args:
        size_bytes: File size in bytes.

    Returns:
        Formatted string (e.g. '1.2 MB', '340 KB').
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _judgement_indicator(judgement: RoBJudgement | None) -> str:
    """Return a traffic-light emoji indicator for a RoB judgement.

    Args:
        judgement: The RoBJudgement value, or None.

    Returns:
        A string with emoji and judgement text.
    """
    if judgement is None:
        return "\u2b1c N/A"
    return JUDGEMENT_INDICATORS.get(judgement, f"\u2753 {judgement.value}")


def _results_to_summary_df(results: list[RoBResult]) -> pd.DataFrame:
    """Build a traffic-light summary DataFrame from RoBResult list.

    Each row is a study (record_id). Each column is a domain.
    Cell values are the judgement indicators.

    Args:
        results: List of completed RoBResult objects.

    Returns:
        DataFrame with studies as rows and domains as columns.
    """
    rows: list[dict[str, str]] = []
    for result in results:
        row: dict[str, str] = {"Study": result.record_id}
        for domain_result in result.domains:
            domain_label = domain_result.domain.value.replace("_", " ").title()
            row[domain_label] = _judgement_indicator(domain_result.judgement)
        row["Overall"] = _judgement_indicator(result.overall_judgement)
        rows.append(row)
    return pd.DataFrame(rows)


def _results_to_json(results: list[RoBResult]) -> str:
    """Serialize a list of RoBResult to a JSON string.

    Args:
        results: List of RoBResult objects.

    Returns:
        Pretty-printed JSON string.
    """
    return json.dumps(
        [r.model_dump(mode="json") for r in results],
        indent=2,
        default=str,
    )


def _results_to_excel_bytes(results: list[RoBResult]) -> bytes:
    """Serialize a list of RoBResult to an Excel file in memory.

    Creates two sheets: 'Summary' with the traffic-light table and
    'Details' with per-domain rationales and model judgements.

    Args:
        results: List of RoBResult objects.

    Returns:
        Bytes of the Excel file.
    """
    summary_df = _results_to_summary_df(results)

    detail_rows: list[dict[str, Any]] = []
    for result in results:
        for domain_result in result.domains:
            detail_rows.append({
                "Study": result.record_id,
                "Tool": result.tool,
                "Domain": domain_result.domain.value,
                "Judgement": domain_result.judgement.value,
                "Consensus": "Yes" if domain_result.consensus_reached else "No",
                "Rationale": domain_result.rationale,
                "Supporting Quotes": "; ".join(domain_result.supporting_quotes[:3]),
                "Model Judgements": ", ".join(
                    f"{mid}={j.value}"
                    for mid, j in domain_result.model_judgements.items()
                ),
            })
    detail_df = pd.DataFrame(detail_rows)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        detail_df.to_excel(writer, sheet_name="Details", index=False)
    return buffer.getvalue()


def _extract_pdf_text(uploaded_file: Any) -> tuple[str, str]:  # noqa: ANN401
    """Extract text from a Streamlit UploadedFile PDF.

    Writes the file to a temporary location and uses the project's
    PDF parser.

    Args:
        uploaded_file: Streamlit UploadedFile object.

    Returns:
        Tuple of (filename, extracted_text).
    """
    from metascreener.io.pdf_parser import extract_text_from_pdf  # noqa: PLC0415

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = Path(tmp.name)

    try:
        text = extract_text_from_pdf(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return uploaded_file.name, text


def _create_backends(api_key: str) -> list[Any]:
    """Create OpenRouter LLM backends from the model config.

    Args:
        api_key: OpenRouter API key.

    Returns:
        List of OpenRouterAdapter instances.
    """
    from metascreener.config import load_model_config  # noqa: PLC0415
    from metascreener.llm.adapters.openrouter import OpenRouterAdapter  # noqa: PLC0415

    config_path = Path(__file__).resolve().parents[4] / "configs" / "models.yaml"
    if not config_path.exists():
        st.error(f"Model config not found at {config_path}")
        return []

    config = load_model_config(config_path)
    backends: list[Any] = []
    for key, entry in config.models.items():
        if entry.provider == "openrouter":
            backends.append(
                OpenRouterAdapter(
                    model_id=key,
                    openrouter_model_name=entry.model_id,
                    api_key=api_key,
                    model_version=entry.version,
                    timeout_s=config.inference.timeout_s,
                    max_retries=config.inference.max_retries,
                )
            )
    return backends


async def _run_assessment(
    pdf_files: list[Any],
    tool_name: str,
    seed: int,
    api_key: str,
) -> list[RoBResult]:
    """Run RoB assessment on uploaded PDF files.

    Args:
        pdf_files: List of Streamlit UploadedFile objects.
        tool_name: Tool identifier ('rob2', 'robins_i', 'quadas2').
        seed: Reproducibility seed.
        api_key: OpenRouter API key.

    Returns:
        List of RoBResult objects, one per PDF.
    """
    from metascreener.module3_quality.assessor import RoBAssessor  # noqa: PLC0415

    backends = _create_backends(api_key)
    if not backends:
        st.error("No LLM backends could be created. Check your configuration.")
        return []

    assessor = RoBAssessor(backends=backends)
    results: list[RoBResult] = []

    for uploaded_file in pdf_files:
        filename, text = _extract_pdf_text(uploaded_file)

        if not text.strip():
            st.warning(f"No text extracted from {filename}. Skipping.")
            continue

        record_id = Path(filename).stem
        result = await assessor.assess(
            text=text,
            tool_name=tool_name,
            record_id=record_id,
            seed=seed,
        )
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _render_sidebar() -> tuple[str, int, list[Any]]:
    """Render the sidebar configuration controls.

    Returns:
        Tuple of (selected_tool_name, seed, uploaded_pdf_files).
    """
    with st.sidebar:
        st.header("Configuration")

        # Tool selection with descriptions
        st.subheader("Assessment Tool")
        tool_keys = list(TOOL_OPTIONS.keys())
        tool_labels = [TOOL_OPTIONS[k]["label"] for k in tool_keys]
        selected_idx = st.radio(
            "Select tool",
            options=range(len(tool_keys)),
            format_func=lambda i: tool_labels[i],
            index=0,
            label_visibility="collapsed",
        )
        selected_tool = tool_keys[selected_idx]
        st.caption(TOOL_OPTIONS[selected_tool]["description"])

        st.markdown("---")

        # Seed input
        seed = st.number_input(
            "Random seed",
            min_value=0,
            max_value=999999,
            value=DEFAULT_SEED,
            step=1,
            help="Seed for reproducible LLM inference (default: 42)",
        )

        st.markdown("---")

        # PDF upload
        pdf_files = st.file_uploader(
            "Upload PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            help="PDF files of studies to assess",
        )

    return selected_tool, int(seed), pdf_files if pdf_files else []


# ---------------------------------------------------------------------------
# Main content sections
# ---------------------------------------------------------------------------


def _render_pdf_list(pdf_files: list[Any]) -> None:
    """Display uploaded PDF files with names and sizes.

    Args:
        pdf_files: List of Streamlit UploadedFile objects.
    """
    if not pdf_files:
        st.info("Upload PDF files in the sidebar to begin assessment.")
        return

    st.subheader(f"Uploaded PDFs ({len(pdf_files)})")
    for pdf in pdf_files:
        size_str = _format_file_size(pdf.size)
        st.markdown(f"- **{pdf.name}** ({size_str})")


def _render_assessment_controls(
    pdf_files: list[Any],
    tool_name: str,
    seed: int,
) -> None:
    """Render the Run Assessment button and execute if clicked.

    Args:
        pdf_files: List of Streamlit UploadedFile objects.
        tool_name: Selected tool identifier.
        seed: Reproducibility seed.
    """
    st.markdown("---")

    if st.button("Run Assessment", type="primary", disabled=not pdf_files):
        api_key = os.environ.get("OPENROUTER_API_KEY", "")

        if not api_key:
            st.warning(
                "OPENROUTER_API_KEY is not set in your environment. "
                "Please set it before running the assessment:\n\n"
                "```bash\nexport OPENROUTER_API_KEY='your-key-here'\n```"
            )
            return

        with st.status("Assessing quality...", expanded=True) as status:
            st.write(
                f"Tool: **{TOOL_OPTIONS[tool_name]['label']}** | "
                f"Seed: **{seed}** | "
                f"PDFs: **{len(pdf_files)}**"
            )

            try:
                results = asyncio.run(
                    _run_assessment(pdf_files, tool_name, seed, api_key)
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Assessment failed: {exc}")
                status.update(label="Assessment failed", state="error")
                return

            if results:
                st.session_state["rob_results"] = results
                status.update(
                    label=f"Assessment complete ({len(results)} studies)",
                    state="complete",
                )
            else:
                st.warning("No results produced. Check that PDFs contain extractable text.")
                status.update(label="No results", state="error")


def _render_results() -> None:
    """Render assessment results from session state."""
    if "rob_results" not in st.session_state:
        return

    results: list[RoBResult] = st.session_state["rob_results"]
    if not results:
        return

    st.markdown("---")
    st.header("Assessment Results")

    # --- Traffic-light summary table ---
    st.subheader("Traffic-Light Summary")
    summary_df = _results_to_summary_df(results)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # --- Overall summary ---
    st.subheader("Overall Judgements")
    cols = st.columns(min(len(results), 4))
    for idx, result in enumerate(results):
        col = cols[idx % len(cols)]
        with col:
            indicator = _judgement_indicator(result.overall_judgement)
            review_flag = " (needs review)" if result.requires_human_review else ""
            st.metric(
                label=result.record_id,
                value=indicator,
                delta=review_flag if review_flag else None,
                delta_color="off",
            )

    # --- Domain drill-down ---
    st.subheader("Domain Details")
    for result in results:
        with st.expander(
            f"{result.record_id} — {result.tool} — "
            f"{_judgement_indicator(result.overall_judgement)}"
        ):
            for domain_result in result.domains:
                domain_label = domain_result.domain.value.replace("_", " ").title()
                indicator = _judgement_indicator(domain_result.judgement)
                consensus_str = (
                    "Yes" if domain_result.consensus_reached
                    else "**No** (needs review)"
                )

                st.markdown(f"#### {domain_label}: {indicator}")
                st.markdown(f"**Consensus reached:** {consensus_str}")

                if domain_result.rationale:
                    st.markdown(f"**Rationale:** {domain_result.rationale}")

                if domain_result.supporting_quotes:
                    st.markdown("**Supporting quotes:**")
                    for quote in domain_result.supporting_quotes[:3]:
                        st.markdown(f"> {quote}")

                if domain_result.model_judgements:
                    st.markdown("**Per-model judgements:**")
                    model_parts = [
                        f"`{mid}`: {_judgement_indicator(j)}"
                        for mid, j in domain_result.model_judgements.items()
                    ]
                    st.markdown(" | ".join(model_parts))

                st.markdown("---")

    # --- Export buttons ---
    st.subheader("Export Results")
    col_json, col_excel = st.columns(2)
    with col_json:
        st.download_button(
            "Download JSON",
            data=_results_to_json(results),
            file_name="rob_results.json",
            mime="application/json",
            use_container_width=True,
        )
    with col_excel:
        st.download_button(
            "Download Excel",
            data=_results_to_excel_bytes(results),
            file_name="rob_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


def _render_reference_section() -> None:
    """Render a reference section explaining the three RoB tools."""
    st.markdown("---")
    with st.expander("Reference: Risk of Bias Assessment Tools"):
        st.markdown(
            """
**RoB 2 (Revised Cochrane Risk-of-Bias Tool)**

Designed for randomized controlled trials (RCTs). Assesses five domains:
1. Randomization process
2. Deviations from intended interventions
3. Missing outcome data
4. Measurement of the outcome
5. Selection of the reported result

Judgements: Low risk / Some concerns / High risk

---

**ROBINS-I (Risk Of Bias In Non-randomized Studies of Interventions)**

Designed for non-randomized studies of interventions. Assesses seven domains:
1. Confounding
2. Selection of participants
3. Classification of interventions
4. Deviations from intended interventions
5. Missing data
6. Measurement of outcomes
7. Selection of the reported result

Judgements: Low / Moderate / Serious / Critical / No information

---

**QUADAS-2 (Quality Assessment of Diagnostic Accuracy Studies)**

Designed for diagnostic accuracy studies. Assesses four domains:
1. Patient selection
2. Index test
3. Reference standard
4. Flow and timing

Each domain is assessed for both risk of bias and applicability concerns.

Judgements: Low / High / Unclear
"""
        )


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Render the risk of bias assessment page."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Quality Assessment",
        page_icon="\u2696\ufe0f",
        layout="wide",
    )
    st.title("Risk of Bias Assessment")
    st.markdown(
        "Assess study quality using **RoB 2**, **ROBINS-I**, or **QUADAS-2** "
        "with multi-LLM consensus."
    )

    # Sidebar configuration
    selected_tool, seed, pdf_files = _render_sidebar()

    # Main content
    _render_pdf_list(pdf_files)
    _render_assessment_controls(pdf_files, selected_tool, seed)
    _render_results()
    _render_reference_section()


if __name__ == "__main__":
    main()
