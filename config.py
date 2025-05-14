import os
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

# --- ADDED: Default Prompt Settings ---
DEFAULT_SYSTEM_PROMPT = "You are an AI assistant for medical literature screening. Provide output in 'LABEL: [Decision]' and 'Justification: [Reasoning]' format."
DEFAULT_OUTPUT_INSTRUCTIONS = (
    "# Screening Task:\n"
    "Based *only* on the abstract provided below, classify the study using ONE of the following labels: INCLUDE, EXCLUDE, or MAYBE.\n"
    "- Use INCLUDE if the abstract clearly meets all critical inclusion criteria and does not meet any exclusion criteria.\n"
    "- Use EXCLUDE if the abstract clearly meets one or more exclusion criteria, or fails to meet critical inclusion criteria.\n"
    "- Use MAYBE if the abstract suggests potential eligibility but requires full-text review to confirm specific criteria.\n\n"
    "Then, provide a brief justification for your decision (1-2 sentences). If MAYBE, specify what needs clarification.\n\n"
    "# Study Abstract:\n"
    "---\n"
    "{abstract}\n"
    "---\n\n"
    "# Your Classification:\n"
    "Format your response EXACTLY as follows (LABEL and Justification on separate lines):\n"
    "LABEL: [Your Decision - INCLUDE, EXCLUDE, or MAYBE]\n"
    "Justification: [Your Brief Justification. If MAYBE, state what needs clarification.]"
).strip().replace('\r', '').replace('\t', '    ')

# --- ADDED: Configuration for PDF Processing ---
TESSERACT_CMD_PATH = os.getenv("TESSERACT_CMD_PATH", None) # Default to None, app/utils will handle if not set
PDF_OCR_THRESHOLD_CHARS = int(os.getenv("PDF_OCR_THRESHOLD_CHARS", 50)) # Default to 50 chars
# --- END ADDED Configuration ---


# --- LLM Provider Configurations ---
SUPPORTED_LLM_PROVIDERS = {
    "DeepSeek": {
        "api_key_env_var": "DEEPSEEK_API_KEY",
        "api_key_session_key": "deepseek_api_key_user",
        "base_url_env_var": "DEEPSEEK_API_BASE_URL",
        "default_base_url": "https://api.deepseek.com",
        "models": [
            {"id": "deepseek-chat", "display_name": "DeepSeek Chat (General)", "type": "chat"},
            {"id": "deepseek-reasoner", "display_name": "DeepSeek Coder (Specialized/Reasoning)", "type": "reasoning"},
        ]
    },
    "OpenAI_ChatGPT": {
        "api_key_env_var": "OPENAI_API_KEY",
        "api_key_session_key": "openai_api_key_user",
        "default_base_url": "https://api.openai.com/v1",
        "models": [
            {"id": "gpt-3.5-turbo", "display_name": "GPT-3.5 Turbo", "type": "chat"},
            {"id": "gpt-4", "display_name": "GPT-4", "type": "reasoning"},
            {"id": "gpt-4-turbo-preview", "display_name": "GPT-4 Turbo", "type": "reasoning"},
            {"id": "gpt-4o", "display_name": "GPT-4o (Omni/Advanced Reasoning)", "type": "reasoning"},
        ]
    },
    "Google_Gemini": {
        "api_key_env_var": "GEMINI_API_KEY",
        "api_key_session_key": "gemini_api_key_user",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": [
            {"id": "gemini-1.0-pro", "display_name": "Gemini 1.0 Pro", "type": "chat"},  # More specific ID
            {"id": "gemini-1.5-pro-latest", "display_name": "Gemini 1.5 Pro (Advanced Reasoning)", "type": "reasoning"},
            {"id": "gemini-1.5-flash-latest", "display_name": "Gemini 1.5 Flash (Fast Chat)", "type": "chat"},
        ]
    },
    "Anthropic_Claude": {
        "api_key_env_var": "ANTHROPIC_API_KEY",
        "api_key_session_key": "anthropic_api_key_user",
        "default_base_url": "https://api.anthropic.com/v1",
        "models": [
            {"id": "claude-3-haiku-20240307", "display_name": "Claude 3 Haiku (Fast Chat)", "type": "chat"},
            {"id": "claude-3-sonnet-20240229", "display_name": "Claude 3 Sonnet (Balanced Reasoning)",
             "type": "reasoning"},
            {"id": "claude-3-opus-20240229", "display_name": "Claude 3 Opus (Max Intelligence)", "type": "reasoning"},
            {"id": "claude-2.1", "display_name": "Claude 2.1 (Older Reasoning)", "type": "reasoning"},
        ]
    }
}

# --- Screening Criteria (Refactored Again) ---
PICOT_TEMPLATE = """
# PICOT Framework for Medical Systematic Review Inclusion and Exclusion Criteria

## P (Population/Patient/Problem):
### Include populations matching:
{p_include}
### Exclude populations matching:
{p_exclude}
### Classify as 'Maybe' if population details are unclear, such as:
{p_maybe}

## I (Intervention):
### Include interventions matching:
{i_include}
### Exclude interventions matching:
{i_exclude}
### Classify as 'Maybe' if intervention details are unclear, such as:
{i_maybe}

## C (Comparison):
### Include comparisons matching:
{c_include}
### Exclude comparisons matching:
{c_exclude}
### Classify as 'Maybe' if comparison details are unclear, such as:
{c_maybe}

## O (Outcome):
### Include outcomes matching:
{o_include}
### Exclude outcomes matching:
{o_exclude}
### Classify as 'Maybe' if outcome details are unclear, such as:
{o_maybe}

## T (Time / Study Type):
### Include time/study types matching:
{t_include}
### Exclude time/study types matching:
{t_exclude}
### Classify as 'Maybe' if time/study details are unclear, such as:
{t_maybe}

## Other Inclusion Criteria:
{other_inclusion}

## Other Exclusion Criteria:
{other_exclusion}

""" # Removed the single Maybe section

# Refactored Default Example Criteria with per-element Maybe
DEFAULT_EXAMPLE_CRITERIA = {
    # Population
    "p_include": """Example Include Criteria:
- Primary population: General population sampled from community settings (households, schools, workplaces, screening programs)
- Includes all ages, both sexes, pregnant women
- Extended populations (community representative): Outpatients (not seeking care for studied infection), health check-up attendees

Tip: Specify target population characteristics such as age range, gender, and specific conditions.""",
    "p_exclude": """Example Exclude Criteria:
- Hospitalized patients (>48 hours)
- Neonates in NICU/special care
- Healthcare workers
- Long-term care residents
- International travelers (<6 months ago)
- Occupational groups (vets, animal handlers, farmers)
- Patients seeking care for the studied infection

Tip: List clear exclusion characteristics, ensure no contradiction with inclusion criteria.""",
    "p_maybe": """Example 'Maybe' Scenarios:
- Community setting mentioned but recruitment method unclear
- Age group mentioned but not precise enough, e.g., just says "children"

Tip: Focus on key population information that might be missing from abstracts, needed for a clear decision.""",
    # Intervention
    "i_include": """Example Include Criteria:
- Observational studies (cross-sectional, cohort, case-control) or RCTs with baseline AMR data
- No specific intervention required

Tip: Clearly state acceptable study types and necessary data requirements.""",
    "i_exclude": """Example Exclude Criteria:
(No specific intervention exclusions defined)

Tip: Specify any intervention types that should be excluded if applicable.""",
    "i_maybe": """Example 'Maybe' Scenarios:
- Data collection described but study design not explicitly named (e.g., sounds cross-sectional but not stated)

Tip: Focus on key intervention/study design details that might be missing from abstracts, needed for a clear decision.""",
    # Comparison
    "c_include": """Example Include Criteria:
- No specific comparison group required

Tip: If specific comparison groups are needed, clearly state requirements.""",
    "c_exclude": """Example Exclude Criteria:
(No specific comparison exclusions defined)

Tip: State any unacceptable comparison group types.""",
    "c_maybe": """Example 'Maybe' Scenarios:
(N/A if no comparison required)

Tip: Focus on key comparison details that might be missing from abstracts, needed for a clear decision (if applicable).""",
    # Outcome
    "o_include": """Example Include Criteria:
- Reports prevalence of Antimicrobial Resistance (AMR) for specified WHO BPPL pathogens (excluding TB, Gonorrhea)

Tip: Specify required outcome measures and measurement methods.""",
    "o_exclude": """Example Exclude Criteria:
- Does not report AMR data
- Focuses only on excluded pathogens (TB, Gonorrhea)

Tip: Clearly indicate which outcomes lead to exclusion.""",
    "o_maybe": """Example 'Maybe' Scenarios:
- Mentions resistance testing but doesn't specify pathogens
- Mentions relevant pathogen but unclear if AMR prevalence reported

Tip: Focus on key outcome details that might be missing from abstracts, needed for a clear decision.""",
    # Time/Study Type
    "t_include": """Example Include Criteria:
- Any publication year
- Any geographic location
- Original research articles

Tip: State time range and acceptable study types.""",
    "t_exclude": """Example Exclude Criteria:
- Systematic reviews, meta-analyses, review articles, editorials, commentaries, policy papers
- Case reports/series (<10 cases)
- Studies conducted only during known pathogen outbreaks

Tip: List non-compliant study types and temporal characteristics.""",
    "t_maybe": """Example 'Maybe' Scenarios:
- Abstract doesn't clearly state if it's original research vs. review type

Tip: Focus on key study type/publication details that might be missing from abstracts, needed for a clear decision.""",
    # Other
    "other_inclusion": """Example Other Inclusion Criteria:
(No other specific inclusion criteria defined)

Tip: Add any necessary inclusion criteria not covered by PICOT framework.""",
    "other_exclusion": """Example Other Exclusion Criteria:
(No other specific exclusion criteria defined)

Tip: Add any necessary exclusion criteria not covered by PICOT framework."""
}

# USER_CRITERIA will hold the user's overrides, including potentially the new fields
USER_CRITERIA = None


# --- Getter Functions ---
def get_llm_providers_info():
    return SUPPORTED_LLM_PROVIDERS


def get_current_criteria_object() -> Dict:
    global USER_CRITERIA
    if USER_CRITERIA is not None:
        return USER_CRITERIA
    else:
        return DEFAULT_EXAMPLE_CRITERIA


def get_current_llm_config(session_data):
    default_provider_name = list(SUPPORTED_LLM_PROVIDERS.keys())[0]
    provider_name = session_data.get("selected_llm_provider", default_provider_name)
    if provider_name not in SUPPORTED_LLM_PROVIDERS:
        provider_name = default_provider_name
    provider_config = SUPPORTED_LLM_PROVIDERS[provider_name]
    default_model_id = provider_config["models"][0]["id"] if provider_config["models"] else None
    model_id = session_data.get("selected_llm_model_id", default_model_id)
    if not model_id or model_id not in [m['id'] for m in
                                        provider_config['models']]:  # check if model is valid for provider
        model_id = default_model_id
    return {
        "provider_name": provider_name, "model_id": model_id, "config": provider_config
    }


def get_api_key_for_provider(provider_name, session_data):
    if provider_name not in SUPPORTED_LLM_PROVIDERS: return None
    provider_config = SUPPORTED_LLM_PROVIDERS[provider_name]
    session_key = provider_config.get("api_key_session_key")
    env_var_name = provider_config.get("api_key_env_var")
    if session_key and session_key in session_data and session_data[session_key]:
        return session_data[session_key]
    if env_var_name and os.getenv(env_var_name):
        return os.getenv(env_var_name)
    return None


def get_base_url_for_provider(provider_name):
    if provider_name not in SUPPORTED_LLM_PROVIDERS: return None
    provider_config = SUPPORTED_LLM_PROVIDERS[provider_name]
    return os.getenv(provider_config.get("base_url_env_var", ""), provider_config["default_base_url"])


def get_screening_criteria() -> str:
    current_criteria_dict = get_current_criteria_object()
    # Format using the new template with all sub-fields
    return PICOT_TEMPLATE.format(
        p_include=current_criteria_dict.get("p_include", ""),
        p_exclude=current_criteria_dict.get("p_exclude", ""),
        p_maybe=current_criteria_dict.get("p_maybe", ""),
        i_include=current_criteria_dict.get("i_include", ""),
        i_exclude=current_criteria_dict.get("i_exclude", ""),
        i_maybe=current_criteria_dict.get("i_maybe", ""),
        c_include=current_criteria_dict.get("c_include", ""),
        c_exclude=current_criteria_dict.get("c_exclude", ""),
        c_maybe=current_criteria_dict.get("c_maybe", ""),
        o_include=current_criteria_dict.get("o_include", ""),
        o_exclude=current_criteria_dict.get("o_exclude", ""),
        o_maybe=current_criteria_dict.get("o_maybe", ""),
        t_include=current_criteria_dict.get("t_include", ""),
        t_exclude=current_criteria_dict.get("t_exclude", ""),
        t_maybe=current_criteria_dict.get("t_maybe", ""),
        other_inclusion=current_criteria_dict.get("other_inclusion", ""),
        other_exclusion=current_criteria_dict.get("other_exclusion", ""),
    ).strip() # Added strip() for cleaner output


def set_user_criteria(criteria_dict):
    global USER_CRITERIA
    USER_CRITERIA = criteria_dict


def reset_to_default_criteria():
    global USER_CRITERIA
    USER_CRITERIA = None