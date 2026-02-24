"""Streamlit page for the Criteria Wizard."""
from __future__ import annotations

import streamlit as st

from metascreener.core.enums import CriteriaFramework, CriteriaInputMode, WizardMode


def main() -> None:
    """Render the criteria wizard page."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Criteria Wizard",
        page_icon="\U0001f52c",
        layout="wide",
    )
    st.title("Criteria Wizard")
    st.markdown("Define your systematic review criteria using AI assistance.")

    # ------------------------------------------------------------------
    # Sidebar controls
    # ------------------------------------------------------------------
    with st.sidebar:
        st.header("Configuration")

        input_mode = st.selectbox(
            "Input mode",
            options=[m.value for m in CriteriaInputMode],
            index=1,  # default to "topic"
            help="How you want to provide input",
        )

        wizard_mode = st.selectbox(
            "Wizard mode",
            options=[m.value for m in WizardMode],
            index=0,  # default to "smart"
            help="Smart: AI generates + you refine issues. Guided: step-by-step.",
        )

        framework = st.selectbox(
            "Framework",
            options=["auto"] + [
                f.value for f in CriteriaFramework if f != CriteriaFramework.CUSTOM
            ],
            index=0,
            help="Auto-detect or specify the SR framework",
        )

        output_path = st.text_input(
            "Output path",
            value="criteria.yaml",
            help="Where to save the criteria file",
        )

    # ------------------------------------------------------------------
    # Main input area
    # ------------------------------------------------------------------
    user_input: str = ""

    if input_mode == CriteriaInputMode.TOPIC.value:
        user_input = st.text_area(
            "Research topic",
            placeholder=(
                "e.g., Effect of antimicrobial stewardship on "
                "mortality in adult ICU patients"
            ),
            height=100,
        )
    elif input_mode == CriteriaInputMode.TEXT.value:
        user_input = st.text_area(
            "Criteria text",
            placeholder="Paste your inclusion/exclusion criteria here...",
            height=200,
        )
    elif input_mode == CriteriaInputMode.YAML.value:
        uploaded = st.file_uploader("Upload criteria YAML", type=["yaml", "yml"])
        user_input = uploaded.read().decode("utf-8") if uploaded else ""
    else:
        user_input = st.text_area("Input", height=100)

    # ------------------------------------------------------------------
    # Template selection
    # ------------------------------------------------------------------
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Or start from a template")
    with col2:
        if st.button("Load templates"):
            try:
                from metascreener.criteria.templates import (  # noqa: PLC0415
                    TemplateLibrary,
                )

                lib = TemplateLibrary()
                st.session_state["templates"] = lib.list_all()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error loading templates: {exc}")

    if "templates" in st.session_state:
        for tpl in st.session_state["templates"]:
            with st.expander(f"{tpl.name} ({tpl.framework.value})"):
                st.markdown(f"**Description:** {tpl.description}")
                st.markdown(f"**Tags:** {', '.join(tpl.tags)}")
                st.markdown(
                    f"**Elements:** {', '.join(tpl.elements.keys())}"
                )
                if st.button(
                    f"Use {tpl.name}", key=f"use_{tpl.template_id}"
                ):
                    st.info(
                        f"Template '{tpl.name}' selected. "
                        f"Fill in details above and click Generate."
                    )

    # ------------------------------------------------------------------
    # Generate button
    # ------------------------------------------------------------------
    st.markdown("---")
    if st.button("Generate Criteria", type="primary", disabled=not user_input):
        st.info(
            "Full wizard execution requires LLM backend configuration. "
            "Configure API keys in your environment and retry."
        )
        st.markdown(
            "**Quick start:** Set `OPENROUTER_API_KEY` environment variable, "
            "then click Generate again."
        )

    # ------------------------------------------------------------------
    # Display existing criteria if loaded
    # ------------------------------------------------------------------
    if "criteria" in st.session_state:
        st.markdown("---")
        st.subheader("Generated Criteria")
        criteria = st.session_state["criteria"]
        st.json(criteria.model_dump(mode="json", exclude_none=True))

    # Suppress unused-variable warnings for sidebar selections that are
    # used only when the wizard is fully wired up.
    _ = wizard_mode, framework, output_path


if __name__ == "__main__":
    main()
else:
    main()
