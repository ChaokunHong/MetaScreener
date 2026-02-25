"""Streamlit page for the Criteria Wizard.

Provides a full-featured UI for defining systematic review criteria:
- Input via topic, free text, or YAML upload
- Template browser with one-click loading
- AI-powered criteria generation with progress indicators
- YAML preview with syntax highlighting
- Download and refinement support
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st
import yaml

from metascreener.core.enums import CriteriaFramework, CriteriaInputMode, WizardMode
from metascreener.core.models import CriteriaElement, CriteriaTemplate, ReviewCriteria
from metascreener.criteria.schema import CriteriaSchema
from metascreener.criteria.templates import TemplateLibrary

# ---------------------------------------------------------------------------
# Session state keys
# ---------------------------------------------------------------------------
_SK_CRITERIA = "criteria"
_SK_YAML = "criteria_yaml"
_SK_TEMPLATES = "templates"
_SK_GENERATION_LOG = "generation_log"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _criteria_to_yaml(criteria: ReviewCriteria) -> str:
    """Serialize ReviewCriteria to a YAML string.

    Args:
        criteria: The criteria object to serialize.

    Returns:
        YAML-formatted string representation.
    """
    data = criteria.model_dump(mode="json", exclude_none=True)
    return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _load_templates() -> list[CriteriaTemplate]:
    """Load all built-in templates from the template library.

    Returns:
        List of available criteria templates.
    """
    lib = TemplateLibrary()
    return lib.list_all()


def _template_to_criteria(template: CriteriaTemplate) -> ReviewCriteria:
    """Convert a CriteriaTemplate into a ReviewCriteria object.

    Args:
        template: The template to convert.

    Returns:
        ReviewCriteria populated from the template.
    """
    return ReviewCriteria(
        framework=template.framework,
        research_question=f"Review based on template: {template.name}",
        elements=dict(template.elements),
        required_elements=list(template.elements.keys()),
        study_design_include=list(template.study_design_include),
    )


def _apply_refinement_command(criteria: ReviewCriteria, command: str) -> list[str]:
    """Parse and apply refinement commands to criteria.

    Supports syntax:
    - ``+term`` or ``add: term`` to add to include lists
    - ``-term`` or ``remove: term`` to remove terms
    - ``exclude: term`` to add to exclude lists
    - ``element_name: +term`` to target a specific element

    Args:
        criteria: Criteria to modify in-place.
        command: The refinement command string.

    Returns:
        List of status messages describing actions taken.
    """
    messages: list[str] = []
    for line in command.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # Check for element-targeted commands: "population: +adults"
        target_element: str | None = None
        if ":" in line and not line.startswith(("+", "-", "add:", "remove:", "exclude:")):
            parts = line.split(":", 1)
            candidate_key = parts[0].strip().lower()
            if candidate_key in criteria.elements:
                target_element = candidate_key
                line = parts[1].strip()

        elements_to_modify = (
            {target_element: criteria.elements[target_element]}
            if target_element and target_element in criteria.elements
            else dict(criteria.elements)
        )

        if line.startswith("+"):
            term = line[1:].strip()
            if term:
                for key, elem in elements_to_modify.items():
                    if term not in elem.include:
                        elem.include.append(term)
                        messages.append(f"Added '{term}' to {key} include list")
                        break

        elif line.startswith("-"):
            term = line[1:].strip()
            if term:
                for key, elem in elements_to_modify.items():
                    if term in elem.include:
                        elem.include.remove(term)
                        messages.append(f"Removed '{term}' from {key} include list")
                    if term in elem.exclude:
                        elem.exclude.remove(term)
                        messages.append(f"Removed '{term}' from {key} exclude list")

        elif line.lower().startswith("add:"):
            term = line[4:].strip()
            if term:
                for key, elem in elements_to_modify.items():
                    if term not in elem.include:
                        elem.include.append(term)
                        messages.append(f"Added '{term}' to {key} include list")
                        break

        elif line.lower().startswith("remove:"):
            term = line[7:].strip()
            if term:
                for key, elem in elements_to_modify.items():
                    if term in elem.include:
                        elem.include.remove(term)
                        messages.append(f"Removed '{term}' from {key} include list")
                    if term in elem.exclude:
                        elem.exclude.remove(term)
                        messages.append(f"Removed '{term}' from {key} exclude list")

        elif line.lower().startswith("exclude:"):
            term = line[8:].strip()
            if term:
                for key, elem in elements_to_modify.items():
                    if term not in elem.exclude:
                        elem.exclude.append(term)
                        messages.append(f"Added '{term}' to {key} exclude list")
                        break

        else:
            messages.append(f"Unrecognized command: '{line}'")

    return messages


async def _run_wizard(
    user_input: str,
    input_mode: CriteriaInputMode,
    wizard_mode: WizardMode,
    framework_str: str,
    seed: int,
    status_container: st.delta_generator.DeltaGenerator,
) -> ReviewCriteria:
    """Run the CriteriaWizard asynchronously with UI status callbacks.

    Args:
        user_input: Raw user input text.
        input_mode: Input mode selection.
        wizard_mode: Wizard mode selection.
        framework_str: Framework string or "auto".
        seed: Random seed for reproducibility.
        status_container: Streamlit container for status updates.

    Returns:
        Generated ReviewCriteria.

    Raises:
        Exception: Propagates any wizard errors for caller handling.
    """
    from metascreener.criteria.wizard import CriteriaWizard  # noqa: PLC0415
    from metascreener.llm.adapters.openrouter import OpenRouterAdapter  # noqa: PLC0415

    status_log: list[str] = []

    async def show_status(msg: str) -> None:
        """Write status updates to the Streamlit container."""
        status_log.append(msg)
        status_container.text(msg)

    async def ask_user(question: str) -> str:
        """Return empty string for non-interactive mode."""
        _ = question
        return ""

    async def confirm(question: str) -> bool:
        """Return True for non-interactive mode."""
        _ = question
        return True

    # Build backends from environment
    import os  # noqa: PLC0415

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        msg = (
            "OPENROUTER_API_KEY environment variable is not set. "
            "Please configure your API key to enable AI-powered generation."
        )
        raise RuntimeError(msg)

    backend = OpenRouterAdapter(
        model_id="qwen3",
        openrouter_model_name="qwen/qwen3-235b-a22b",
        api_key=api_key,
        model_version="2025-04-28",
    )

    override_framework: CriteriaFramework | None = None
    if framework_str != "auto":
        override_framework = CriteriaFramework(framework_str)

    wizard = CriteriaWizard(
        generation_backends=[backend],
        detector_backend=backend,
        quality_backend=backend,
    )

    criteria = await wizard.run(
        input_mode=input_mode,
        wizard_mode=wizard_mode,
        raw_input=user_input,
        ask_user=ask_user,
        show_status=show_status,
        confirm=confirm,
        override_framework=override_framework,
        seed=seed,
    )

    st.session_state[_SK_GENERATION_LOG] = status_log
    return criteria


# ---------------------------------------------------------------------------
# UI Rendering Functions
# ---------------------------------------------------------------------------


def _render_sidebar() -> tuple[str, str, str, str, int]:
    """Render sidebar configuration controls.

    Returns:
        Tuple of (input_mode, wizard_mode, framework, output_path, seed).
    """
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
            help="Smart: AI generates + you refine. Guided: step-by-step.",
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

        seed = st.number_input(
            "Random seed",
            value=42,
            min_value=0,
            help="Seed for reproducible generation",
        )

        # API key status
        import os  # noqa: PLC0415

        st.markdown("---")
        st.subheader("API Status")
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if api_key:
            st.success("API key configured")
        else:
            st.warning("OPENROUTER_API_KEY not set")
            st.caption("Set this environment variable to enable AI generation.")

    return str(input_mode), str(wizard_mode), str(framework), str(output_path), int(seed)


def _render_input_area(input_mode: str) -> str:
    """Render the main input area based on selected mode.

    Args:
        input_mode: The selected input mode string.

    Returns:
        User-provided input text.
    """
    st.subheader("Input")
    user_input: str = ""

    if input_mode == CriteriaInputMode.TOPIC.value:
        user_input = st.text_area(
            "Research topic",
            placeholder=(
                "e.g., Effect of antimicrobial stewardship on "
                "mortality in adult ICU patients"
            ),
            height=100,
            help="Describe your research question or topic. The AI will generate criteria.",
        )
    elif input_mode == CriteriaInputMode.TEXT.value:
        user_input = st.text_area(
            "Criteria text",
            placeholder=(
                "Paste your inclusion/exclusion criteria here...\n\n"
                "Example:\n"
                "Include: Adults over 18, randomized controlled trials\n"
                "Exclude: Animal studies, case reports"
            ),
            height=200,
            help="Paste existing criteria text for AI parsing and structuring.",
        )
    elif input_mode == CriteriaInputMode.YAML.value:
        uploaded = st.file_uploader(
            "Upload criteria YAML",
            type=["yaml", "yml"],
            help="Upload a previously saved criteria.yaml file",
        )
        if uploaded is not None:
            user_input = uploaded.read().decode("utf-8")
            if user_input:
                st.success("YAML file loaded successfully")
    else:
        user_input = st.text_area(
            "Input",
            height=100,
            help="Provide your input for criteria generation.",
        )

    return user_input


def _render_template_browser() -> None:
    """Render the template browser section with expandable cards."""
    st.subheader("Templates")
    st.caption(
        "Start from a pre-built template for common review types. "
        "Click 'Use this template' to populate the criteria."
    )

    # Load templates on first run
    if _SK_TEMPLATES not in st.session_state:
        try:
            st.session_state[_SK_TEMPLATES] = _load_templates()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error loading templates: {exc}")
            return

    templates: list[CriteriaTemplate] = st.session_state[_SK_TEMPLATES]

    if not templates:
        st.info("No built-in templates found.")
        return

    # Display templates in a grid of columns
    cols_per_row = 3
    for row_start in range(0, len(templates), cols_per_row):
        row_templates = templates[row_start : row_start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, tpl in zip(cols, row_templates, strict=False):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{tpl.name}**")
                    st.caption(f"Framework: {tpl.framework.value.upper()}")
                    st.markdown(
                        f"<span style='font-size:0.85rem;'>{tpl.description}</span>",
                        unsafe_allow_html=True,
                    )
                    if tpl.tags:
                        tag_str = " ".join(f"`{t}`" for t in tpl.tags)
                        st.markdown(tag_str)

                    n_elements = len(tpl.elements)
                    n_designs = len(tpl.study_design_include)
                    st.caption(f"{n_elements} elements, {n_designs} study designs")

                    if st.button(
                        "Use this template",
                        key=f"use_{tpl.template_id}",
                        use_container_width=True,
                    ):
                        criteria = _template_to_criteria(tpl)
                        st.session_state[_SK_CRITERIA] = criteria
                        st.session_state[_SK_YAML] = _criteria_to_yaml(criteria)
                        st.rerun()

    # Show template details in expanders below the grid
    with st.expander("View template details"):
        for tpl in templates:
            st.markdown(f"### {tpl.name}")
            st.markdown(f"**Framework:** {tpl.framework.value.upper()}")
            st.markdown(f"**Description:** {tpl.description}")
            for key, elem in tpl.elements.items():
                include_str = ", ".join(elem.include) if elem.include else "(none)"
                exclude_str = ", ".join(elem.exclude) if elem.exclude else "(none)"
                st.markdown(
                    f"- **{elem.name}** ({key}): "
                    f"Include: {include_str} | Exclude: {exclude_str}"
                )
            if tpl.study_design_include:
                st.markdown(
                    f"- **Study designs:** {', '.join(tpl.study_design_include)}"
                )
            st.markdown("---")


def _render_generation_section(
    user_input: str,
    input_mode: str,
    wizard_mode: str,
    framework: str,
    seed: int,
) -> None:
    """Render the criteria generation section with progress indicators.

    Args:
        user_input: User-provided input text.
        input_mode: Selected input mode.
        wizard_mode: Selected wizard mode.
        framework: Selected framework or "auto".
        seed: Random seed.
    """
    st.subheader("Generate Criteria")

    col_gen, col_help = st.columns([2, 3])
    with col_gen:
        generate_clicked = st.button(
            "Generate Criteria",
            type="primary",
            disabled=not user_input,
            use_container_width=True,
        )
    with col_help:
        if not user_input:
            st.caption("Enter a topic or text above, or select a template to begin.")

    if generate_clicked and user_input:
        status_container = st.empty()

        with st.status("Generating criteria...", expanded=True) as status:
            progress_bar = st.progress(0, text="Starting wizard...")

            try:
                # Step 1: Parse input mode
                progress_bar.progress(10, text="Preparing input...")
                criteria_input_mode = CriteriaInputMode(input_mode)
                criteria_wizard_mode = WizardMode(wizard_mode)

                # For YAML input, parse directly without LLM
                if criteria_input_mode == CriteriaInputMode.YAML:
                    progress_bar.progress(50, text="Parsing YAML...")
                    fw = (
                        CriteriaFramework(framework)
                        if framework != "auto"
                        else CriteriaFramework.PICO
                    )
                    criteria = CriteriaSchema.load_from_string(user_input, fw)
                    progress_bar.progress(100, text="YAML parsed successfully")
                else:
                    # Try running the full wizard
                    progress_bar.progress(20, text="Connecting to LLM backend...")

                    loop = asyncio.new_event_loop()
                    try:
                        criteria = loop.run_until_complete(
                            _run_wizard(
                                user_input=user_input,
                                input_mode=criteria_input_mode,
                                wizard_mode=criteria_wizard_mode,
                                framework_str=framework,
                                seed=seed,
                                status_container=status_container,
                            )
                        )
                    finally:
                        loop.close()

                    progress_bar.progress(100, text="Generation complete")

                # Store results in session state
                st.session_state[_SK_CRITERIA] = criteria
                st.session_state[_SK_YAML] = _criteria_to_yaml(criteria)
                status.update(label="Criteria generated successfully", state="complete")

            except RuntimeError as exc:
                # API key not configured -- show helpful message with a preview
                progress_bar.progress(100, text="Generation requires API access")
                status.update(label="API key required", state="error")
                st.warning(str(exc))

                st.info(
                    "Without an API key, here is a preview of what the output "
                    "structure looks like based on your input:"
                )
                _show_preview_criteria(user_input, framework)

            except Exception as exc:  # noqa: BLE001
                progress_bar.progress(100, text="Error during generation")
                status.update(label="Generation failed", state="error")
                st.error(f"Error during criteria generation: {exc}")

                st.info(
                    "Showing a structural preview instead. Configure your "
                    "API key for full AI-powered generation."
                )
                _show_preview_criteria(user_input, framework)


def _show_preview_criteria(user_input: str, framework_str: str) -> None:
    """Display a preview criteria structure when LLM is unavailable.

    Creates a placeholder ReviewCriteria based on the framework and
    user input to demonstrate the expected output format.

    Args:
        user_input: The user's input text.
        framework_str: The selected framework string.
    """
    fw = (
        CriteriaFramework(framework_str)
        if framework_str != "auto"
        else CriteriaFramework.PICO
    )

    # Build framework-appropriate placeholder elements
    element_keys = _get_framework_elements(fw)
    elements: dict[str, CriteriaElement] = {}
    for key, name in element_keys:
        elements[key] = CriteriaElement(
            name=name,
            include=[f"<define {name.lower()} inclusion criteria>"],
            exclude=[f"<define {name.lower()} exclusion criteria>"],
        )

    preview = ReviewCriteria(
        framework=fw,
        research_question=user_input[:200] if user_input else None,
        elements=elements,
        required_elements=[k for k, _ in element_keys],
        study_design_include=["<specify study designs>"],
    )

    preview_yaml = _criteria_to_yaml(preview)
    st.session_state[_SK_CRITERIA] = preview
    st.session_state[_SK_YAML] = preview_yaml


def _get_framework_elements(framework: CriteriaFramework) -> list[tuple[str, str]]:
    """Return element key-name pairs for a given framework.

    Args:
        framework: The criteria framework type.

    Returns:
        List of (key, display_name) tuples for the framework elements.
    """
    framework_elements: dict[CriteriaFramework, list[tuple[str, str]]] = {
        CriteriaFramework.PICO: [
            ("population", "Population"),
            ("intervention", "Intervention"),
            ("comparison", "Comparison"),
            ("outcome", "Outcome"),
        ],
        CriteriaFramework.PEO: [
            ("population", "Population"),
            ("exposure", "Exposure"),
            ("outcome", "Outcome"),
        ],
        CriteriaFramework.SPIDER: [
            ("sample", "Sample"),
            ("phenomenon", "Phenomenon of Interest"),
            ("design", "Design"),
            ("evaluation", "Evaluation"),
            ("research_type", "Research Type"),
        ],
        CriteriaFramework.PCC: [
            ("population", "Population"),
            ("concept", "Concept"),
            ("context", "Context"),
        ],
        CriteriaFramework.PIRD: [
            ("population", "Population"),
            ("index_test", "Index Test"),
            ("reference_standard", "Reference Standard"),
            ("diagnosis", "Diagnosis"),
        ],
        CriteriaFramework.PIF: [
            ("population", "Population"),
            ("indicator", "Indicator / Prognostic Factor"),
            ("follow_up", "Follow-up / Outcome"),
        ],
        CriteriaFramework.PECO: [
            ("population", "Population"),
            ("exposure", "Exposure"),
            ("comparator", "Comparator"),
            ("outcome", "Outcome"),
        ],
    }
    return framework_elements.get(framework, framework_elements[CriteriaFramework.PICO])


def _render_criteria_display() -> None:
    """Render the generated criteria with YAML preview and download."""
    if _SK_CRITERIA not in st.session_state:
        return

    criteria: ReviewCriteria = st.session_state[_SK_CRITERIA]
    yaml_content: str = st.session_state.get(_SK_YAML, _criteria_to_yaml(criteria))

    st.markdown("---")
    st.subheader("Generated Criteria")

    # Summary metrics
    col_fw, col_elem, col_qual, col_lang = st.columns(4)
    with col_fw:
        st.metric("Framework", criteria.framework.value.upper())
    with col_elem:
        st.metric("Elements", len(criteria.elements))
    with col_qual:
        quality_str = (
            str(criteria.quality_score.total)
            if criteria.quality_score
            else "N/A"
        )
        st.metric("Quality Score", quality_str)
    with col_lang:
        st.metric("Language", criteria.detected_language.upper())

    # Research question
    if criteria.research_question:
        st.markdown(f"**Research Question:** {criteria.research_question}")

    # Elements detail view
    st.markdown("#### Criteria Elements")
    for key, elem in criteria.elements.items():
        with st.expander(f"{elem.name} ({key})", expanded=True):
            inc_col, exc_col = st.columns(2)
            with inc_col:
                st.markdown("**Include:**")
                if elem.include:
                    for term in elem.include:
                        st.markdown(f"- {term}")
                else:
                    st.caption("(none)")
            with exc_col:
                st.markdown("**Exclude:**")
                if elem.exclude:
                    for term in elem.exclude:
                        st.markdown(f"- {term}")
                else:
                    st.caption("(none)")

            if elem.ambiguity_flags:
                st.warning(f"Ambiguous terms: {', '.join(elem.ambiguity_flags)}")
            if elem.notes:
                st.info(f"Notes: {elem.notes}")

    # Study designs
    if criteria.study_design_include or criteria.study_design_exclude:
        st.markdown("#### Study Designs")
        design_inc, design_exc = st.columns(2)
        with design_inc:
            st.markdown("**Included designs:**")
            for d in criteria.study_design_include:
                st.markdown(f"- {d}")
        with design_exc:
            st.markdown("**Excluded designs:**")
            for d in criteria.study_design_exclude:
                st.markdown(f"- {d}")

    # Quality score details
    if criteria.quality_score:
        st.markdown("#### Quality Assessment")
        qs = criteria.quality_score
        q_cols = st.columns(4)
        with q_cols[0]:
            st.metric("Completeness", f"{qs.completeness}/100")
        with q_cols[1]:
            st.metric("Precision", f"{qs.precision}/100")
        with q_cols[2]:
            st.metric("Consistency", f"{qs.consistency}/100")
        with q_cols[3]:
            st.metric("Actionability", f"{qs.actionability}/100")

        if qs.suggestions:
            with st.expander("Improvement suggestions"):
                for suggestion in qs.suggestions:
                    st.markdown(f"- {suggestion}")

    # YAML preview
    st.markdown("#### YAML Output")
    tab_yaml, tab_json = st.tabs(["YAML", "JSON"])
    with tab_yaml:
        st.code(yaml_content, language="yaml", line_numbers=True)
    with tab_json:
        json_data = criteria.model_dump(mode="json", exclude_none=True)
        import json  # noqa: PLC0415

        st.code(json.dumps(json_data, indent=2, ensure_ascii=False), language="json")

    # Download buttons
    st.markdown("#### Export")
    dl_col1, dl_col2, dl_col3 = st.columns(3)
    with dl_col1:
        st.download_button(
            label="Download criteria.yaml",
            data=yaml_content,
            file_name="criteria.yaml",
            mime="text/yaml",
            use_container_width=True,
        )
    with dl_col2:
        import json as json_mod  # noqa: PLC0415

        json_str = json_mod.dumps(
            criteria.model_dump(mode="json", exclude_none=True),
            indent=2,
            ensure_ascii=False,
        )
        st.download_button(
            label="Download criteria.json",
            data=json_str,
            file_name="criteria.json",
            mime="application/json",
            use_container_width=True,
        )
    with dl_col3:
        if st.button("Save to disk", use_container_width=True):
            try:
                output_path = Path(
                    st.session_state.get("_output_path", "criteria.yaml")
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                CriteriaSchema.save(criteria, output_path)
                st.success(f"Saved to {output_path}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error saving file: {exc}")

    # Generation log
    if _SK_GENERATION_LOG in st.session_state:
        gen_log: list[str] = st.session_state[_SK_GENERATION_LOG]
        if gen_log:
            with st.expander("Generation log"):
                for entry in gen_log:
                    st.text(entry)


def _render_refinement_section() -> None:
    """Render the criteria refinement section for interactive editing."""
    if _SK_CRITERIA not in st.session_state:
        return

    st.markdown("---")
    st.subheader("Refine Criteria")
    st.caption(
        "Use commands to modify criteria elements. "
        "Commands apply to the first matching element unless you specify one."
    )

    # Syntax help
    with st.expander("Refinement syntax help"):
        st.markdown(
            "| Command | Action |\n"
            "|---------|--------|\n"
            "| `+term` | Add term to an include list |\n"
            "| `-term` | Remove term from include/exclude lists |\n"
            "| `add: term` | Add term to an include list |\n"
            "| `remove: term` | Remove term from all lists |\n"
            "| `exclude: term` | Add term to an exclude list |\n"
            "| `population: +adults` | Target a specific element |\n"
            "\n"
            "You can enter multiple commands, one per line."
        )

    # Refinement input
    refinement_input = st.text_area(
        "Refinement commands",
        placeholder=(
            "Examples:\n"
            "+randomized controlled trial\n"
            "-animal studies\n"
            "population: +children aged 5-12\n"
            "exclude: case reports"
        ),
        height=120,
        key="refinement_input",
    )

    if st.button("Apply refinements", disabled=not refinement_input):
        criteria: ReviewCriteria = st.session_state[_SK_CRITERIA]
        messages = _apply_refinement_command(criteria, refinement_input)

        if messages:
            for msg in messages:
                if msg.startswith("Unrecognized"):
                    st.warning(msg)
                else:
                    st.success(msg)

            # Update YAML and trigger re-render
            st.session_state[_SK_YAML] = _criteria_to_yaml(criteria)
            st.rerun()
        else:
            st.info("No changes applied. Check your command syntax.")

    # Manual element editor
    st.markdown("#### Quick Edit")
    criteria = st.session_state[_SK_CRITERIA]
    element_keys = list(criteria.elements.keys())

    if element_keys:
        selected_element = st.selectbox(
            "Select element to edit",
            options=element_keys,
            format_func=lambda k: f"{criteria.elements[k].name} ({k})",
        )

        if selected_element and selected_element in criteria.elements:
            elem = criteria.elements[selected_element]

            edit_inc, edit_exc = st.columns(2)
            with edit_inc:
                new_include = st.text_area(
                    "Include terms (one per line)",
                    value="\n".join(elem.include),
                    height=150,
                    key=f"edit_inc_{selected_element}",
                )
            with edit_exc:
                new_exclude = st.text_area(
                    "Exclude terms (one per line)",
                    value="\n".join(elem.exclude),
                    height=150,
                    key=f"edit_exc_{selected_element}",
                )

            if st.button("Update element", key=f"update_{selected_element}"):
                elem.include = [
                    t.strip() for t in new_include.split("\n") if t.strip()
                ]
                elem.exclude = [
                    t.strip() for t in new_exclude.split("\n") if t.strip()
                ]
                st.session_state[_SK_YAML] = _criteria_to_yaml(criteria)
                st.success(f"Updated {elem.name}")
                st.rerun()


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------


def main() -> None:
    """Render the criteria wizard page."""
    st.set_page_config(
        page_title="MetaScreener \u2014 Criteria Wizard",
        page_icon="\U0001f52c",
        layout="wide",
    )
    st.title("Criteria Wizard")
    st.markdown(
        "Define your systematic review criteria using AI assistance "
        "or start from a built-in template."
    )

    # Sidebar
    input_mode, wizard_mode, framework, output_path, seed = _render_sidebar()

    # Store output path for save-to-disk
    st.session_state["_output_path"] = output_path

    # Main content area with tabs
    tab_input, tab_templates = st.tabs(["Direct Input", "Browse Templates"])

    with tab_input:
        user_input = _render_input_area(input_mode)

        st.markdown("---")
        _render_generation_section(user_input, input_mode, wizard_mode, framework, seed)

    with tab_templates:
        _render_template_browser()

    # Display generated/loaded criteria
    _render_criteria_display()

    # Refinement section
    _render_refinement_section()



if __name__ == "__main__":
    main()
else:
    main()
