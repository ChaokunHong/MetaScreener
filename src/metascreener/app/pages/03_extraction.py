"""Streamlit page for data extraction."""
from __future__ import annotations

import streamlit as st


def main() -> None:
    """Render the data extraction page."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Data Extraction",
        page_icon="\U0001f4cb",
        layout="wide",
    )
    st.title("Data Extraction")
    st.markdown("Extract structured data from included papers.")

    # Sidebar
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

    # Main area
    if form_file is not None:
        st.subheader("Extraction Form")
        form_content = form_file.read().decode("utf-8")
        st.code(form_content, language="yaml")
    else:
        st.info("Upload an extraction form YAML in the sidebar.")

    if pdf_files:
        st.subheader(f"Uploaded PDFs ({len(pdf_files)})")
        for pdf in pdf_files:
            st.text(f"  {pdf.name}")

    # Run button
    st.markdown("---")
    if st.button("Run Extraction", type="primary"):
        st.warning(
            "Full data extraction requires configured LLM backends. "
            "Set OPENROUTER_API_KEY in your environment."
        )

    # Results placeholder
    if "extraction_results" in st.session_state:
        st.subheader("Extraction Results")
        results = st.session_state["extraction_results"]
        st.dataframe(results)

        st.download_button(
            "Export CSV",
            data="field,value\n",  # placeholder
            file_name="extracted_data.csv",
            mime="text/csv",
        )

    # Suppress unused variable warnings
    _ = form_file


if __name__ == "__main__":
    main()
