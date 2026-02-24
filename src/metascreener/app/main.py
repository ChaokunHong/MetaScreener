"""MetaScreener 2.0 -- Streamlit Application."""
from __future__ import annotations

import streamlit as st


def main() -> None:
    """Main Streamlit application entry point."""
    st.set_page_config(
        page_title="MetaScreener 2.0",
        page_icon="\U0001f52c",
        layout="wide",
    )
    st.title("MetaScreener 2.0")
    st.markdown("AI-assisted systematic review screening tool.")
    st.markdown("Use the sidebar to navigate between pages.")


if __name__ == "__main__":
    main()
