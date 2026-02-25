"""Streamlit page for literature screening."""
from __future__ import annotations

import csv
import json
from io import StringIO

import streamlit as st


def main() -> None:
    """Render the screening page."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Screening",
        page_icon="\U0001f50d",
        layout="wide",
    )
    st.title("Literature Screening")
    st.markdown("Screen papers using the Hierarchical Consensus Network.")

    # Sidebar
    with st.sidebar:
        st.header("Input")
        uploaded_file = st.file_uploader(
            "Upload records (CSV/JSON)",
            type=["csv", "json"],
            help="CSV with title and abstract columns, or JSON array",
        )
        criteria_file = st.file_uploader(
            "Upload criteria (YAML)",
            type=["yaml", "yml"],
            help="Structured review criteria file",
        )
        stage = st.selectbox(
            "Screening stage",
            options=["Title/Abstract", "Full Text"],
            index=0,
        )
        seed = st.number_input("Random seed", value=42, min_value=0)

    # Main area
    if uploaded_file is not None:
        st.subheader("Uploaded Records")
        try:
            if uploaded_file.name.endswith(".json"):
                data = json.loads(uploaded_file.read().decode("utf-8"))
                st.dataframe(data[:100])  # Preview first 100
            else:
                content = uploaded_file.read().decode("utf-8")
                reader = csv.DictReader(StringIO(content))
                rows = list(reader)
                st.dataframe(rows[:100])
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error reading file: {exc}")
    else:
        st.info("Upload records in the sidebar to begin screening.")

    # Run screening button
    st.markdown("---")
    if st.button("Run Screening", type="primary"):
        st.warning(
            "Full screening requires configured LLM backends. "
            "Set OPENROUTER_API_KEY in your environment and configure "
            "models in configs/models.yaml."
        )

    # Results section (placeholder)
    if "screening_results" in st.session_state:
        st.subheader("Results")
        st.dataframe(st.session_state["screening_results"])

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Export CSV",
                data="record_id,decision\n",  # placeholder
                file_name="screening_results.csv",
                mime="text/csv",
            )
        with col2:
            st.download_button(
                "Export JSON",
                data="[]",  # placeholder
                file_name="screening_results.json",
                mime="application/json",
            )

    # Suppress unused variable warnings
    _ = criteria_file, stage, seed


if __name__ == "__main__":
    main()
