"""Streamlit page for risk of bias assessment."""
from __future__ import annotations

import streamlit as st

from metascreener.core.enums import RoBJudgement


def main() -> None:
    """Render the risk of bias assessment page."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Quality Assessment",
        page_icon="\u2696\ufe0f",
        layout="wide",
    )
    st.title("Risk of Bias Assessment")
    st.markdown("Assess study quality using RoB 2, ROBINS-I, or QUADAS-2.")

    # Sidebar
    with st.sidebar:
        st.header("Configuration")
        tool = st.selectbox(
            "Assessment tool",
            options=[
                "RoB 2 (RCTs)",
                "ROBINS-I (Observational)",
                "QUADAS-2 (Diagnostic)",
            ],
            index=0,
        )
        pdf_files = st.file_uploader(
            "Upload PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            help="PDF files to assess",
        )

    # Main area
    if pdf_files:
        st.subheader(f"Uploaded PDFs ({len(pdf_files)})")
        for pdf in pdf_files:
            st.text(f"  {pdf.name}")
    else:
        st.info("Upload PDF files in the sidebar to begin assessment.")

    # Run button
    st.markdown("---")
    if st.button("Run Assessment", type="primary"):
        st.warning(
            "Full RoB assessment requires configured LLM backends. "
            "Set OPENROUTER_API_KEY in your environment."
        )

    # Results placeholder
    if "rob_results" in st.session_state:
        st.subheader("Assessment Results")
        rob_results = st.session_state["rob_results"]

        # Display RoB heatmap if available
        try:
            from metascreener.evaluation.visualizer import (  # noqa: PLC0415
                plot_rob_heatmap,
            )

            fig = plot_rob_heatmap(rob_results)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error generating heatmap: {exc}")

        # Overall summary
        st.subheader("Overall Summary")
        for result in rob_results:
            judgement = result.overall_judgement
            color = (
                {
                    RoBJudgement.LOW: "green",
                    RoBJudgement.HIGH: "red",
                    RoBJudgement.UNCLEAR: "orange",
                }.get(judgement, "gray")
                if judgement
                else "gray"
            )
            st.markdown(
                f"**{result.record_id}**: "
                f":{color}[{judgement.value if judgement else 'N/A'}]"
            )

        st.download_button(
            "Export JSON",
            data="[]",  # placeholder
            file_name="rob_results.json",
            mime="application/json",
        )

    # Suppress unused variable warnings
    _ = tool


if __name__ == "__main__":
    main()
