"""MetaScreener 2.0 -- Streamlit Dashboard Homepage."""
from __future__ import annotations

from pathlib import Path

import streamlit as st


def _detect_project_files() -> list[tuple[str, str, bool]]:
    """Detect MetaScreener project files in the current working directory.

    Returns:
        List of (path, description, exists) tuples.
    """
    cwd = Path.cwd()
    checks = [
        ("criteria.yaml", "Review criteria"),
        ("results/screening_results.json", "Screening results"),
        ("results/audit_trail.json", "Audit trail"),
        ("results/evaluation_report.json", "Evaluation report"),
        ("results/extraction_results.json", "Extraction results"),
        ("extraction_form.yaml", "Extraction form"),
        ("export/results.csv", "Exported CSV"),
    ]
    return [(path, label, (cwd / path).exists()) for path, label, in checks]


def main() -> None:
    """Main Streamlit application entry point — dashboard homepage."""
    st.set_page_config(
        page_title="MetaScreener 2.0",
        page_icon="🔬",
        layout="wide",
    )

    # --- Header ---
    st.title("MetaScreener 2.0")
    st.caption(
        "AI-assisted systematic review tool  •  "
        "Hierarchical Consensus Network  •  4 open-source LLMs"
    )

    # --- Workflow Pipeline ---
    st.markdown("---")
    st.subheader("Systematic Review Pipeline")

    cols = st.columns(5)
    steps = [
        ("📋", "Step 0", "Define Criteria", "00_criteria"),
        ("🔍", "Step 1", "Screen Literature", "01_screening"),
        ("📊", "Step 2", "Evaluate Performance", "02_evaluation"),
        ("📝", "Step 3", "Extract Data", "03_extraction"),
        ("⚖️", "Step 4", "Assess Quality", "04_quality"),
    ]
    for col, (icon, step, label, _page) in zip(cols, steps, strict=False):
        with col:
            st.markdown(
                f"<div style='text-align:center; padding:1rem; "
                f"border:1px solid #ddd; border-radius:8px;'>"
                f"<div style='font-size:2rem;'>{icon}</div>"
                f"<div style='font-weight:bold;'>{step}</div>"
                f"<div style='font-size:0.9rem;'>{label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.info(
        "Use the **sidebar** to navigate to each step, "
        "or follow the pipeline from left to right."
    )

    # --- Project Status ---
    st.markdown("---")
    st.subheader("Project Status")

    project_files = _detect_project_files()
    found = [
        (path, desc) for path, desc, exists in project_files if exists
    ]
    missing = [
        (path, desc) for path, desc, exists in project_files if not exists
    ]

    if found:
        for path, label in found:
            st.markdown(f"✅ **{label}** — `{path}`")
    else:
        st.warning("No MetaScreener files found in the current directory.")

    if missing and found:
        with st.expander("Not yet created"):
            for path, label in missing:
                st.markdown(f"⬜ {label} — `{path}`")

    if not found:
        st.markdown(
            "**Getting started:**\n"
            "1. Navigate to **Criteria Wizard** in the sidebar\n"
            "2. Define your review criteria (PICO/PEO/SPIDER/PCC)\n"
            "3. Upload your search results and start screening"
        )

    # --- Sidebar: Settings ---
    with st.sidebar:
        st.header("Settings")

        # API key status
        import os  # noqa: PLC0415

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if api_key:
            st.success("API key configured")
        else:
            st.warning("OPENROUTER_API_KEY not set")
            st.caption("Set this environment variable to enable LLM inference.")

        # Seed
        st.number_input("Global seed", value=42, min_value=0, key="global_seed")

        # Working directory
        st.caption(f"Working directory: `{Path.cwd()}`")

    # --- About ---
    st.markdown("---")
    with st.expander("About MetaScreener"):
        st.markdown(
            "**MetaScreener 2.0** is an open-source tool for AI-assisted systematic "
            "review screening, data extraction, and quality assessment.\n\n"
            "It uses a **Hierarchical Consensus Network (HCN)** with 4 open-source LLMs "
            "(Qwen3, DeepSeek-V3.2, Llama 4 Scout, Mistral Small 3) to provide "
            "reproducible screening decisions with calibrated confidence.\n\n"
            "**Models:** All models are open-source and version-locked for reproducibility.\n\n"
            "**Target:** The Lancet Digital Health"
        )


if __name__ == "__main__":
    main()
