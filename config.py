import os
from dotenv import load_dotenv

load_dotenv()

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

# --- Screening Criteria ---
PICOT_TEMPLATE = """
# PICOT Framework for Medical Systematic Review Inclusion and Exclusion Criteria

## P (Population/Patient/Problem): Research Population/Patient/Problem
{population_criteria}

## I (Intervention): Intervention Measures
{intervention_criteria}

## C (Comparison): Comparison or Control Measures
{comparison_criteria}

## O (Outcome): Outcome Indicators
{outcome_criteria}

## T (Time): Time Factors
{time_criteria}

# Other Inclusion Criteria:
{other_inclusion_criteria}

# Exclusion Criteria:
{exclusion_criteria}
"""

DEFAULT_EXAMPLE_CRITERIA = {
    "population_criteria": """- **Primary population**: General population sampled from community settings (households, schools, workplaces, community screening programs)
- Includes all ages, both sexes, and pregnant women
- Can include individuals with chronic conditions, current/recent infections, or recent antibiotic use IF they were recruited from community settings
- **Extended populations** (considered representative of community carriage):
  - Outpatients, provided they are not seeking care for infections or symptoms related to the specific pathogens being studied
  - Health check-up attendees
  - Community volunteers participating in research""",
    "intervention_criteria": """- Not limited to specific intervention measures
- Can include observational studies, no specific intervention required""",
    "comparison_criteria": """- No specific comparison requirements
- Can include descriptive studies without comparison groups""",
    "outcome_criteria": """- Reports prevalence of AMR among selected pathogens from WHO 2024 Bacterial Priority Pathogens List (BPPL)
- Pathogens include: Acinetobacter baumannii, Pseudomonas aeruginosa, Enterobacterales (including Klebsiella pneumoniae, Escherichia coli, Enterobacter spp., etc.), Staphylococcus aureus, Enterococcus faecium, Streptococcus pneumoniae, Haemophilus influenzae, Salmonella spp., Shigella spp., Group A Streptococci, Group B Streptococci
- Excludes: Mycobacterium tuberculosis and Neisseria gonorrhoeae
- Must report some form of antimicrobial resistance data""",
    "time_criteria": """- No time restrictions
- Studies published in any year can be included""",
    "other_inclusion_criteria": """- Observational studies (cross-sectional, cohort, case-control) or RCTs with baseline AMR data
- Must be original research (not necessarily peer-reviewed at this screening stage)
- No minimum sample size requirement at the title/abstract screening stage
- No language restrictions
- No geographic restrictions (studies from all regions can be included)""",
    "exclusion_criteria": """- **Specific populations**:
  - Hospitalized patients (admitted for >48 hours)
  - Neonates in NICU or special care nurseries
  - Healthcare workers (doctors, nurses, clinical staff)
  - Residents of long-term care facilities (nursing homes)
  - International travelers (with international travel history within 6 months)
  - Occupational groups with unique exposures (veterinarians, animal handlers, pharmaceutical workers, farmers)
  - Clinical patients specifically seeking care for infections related to the studied pathogens
- **Study types**:
  - Systematic reviews/meta-analyses/review articles (though these can be reviewed separately for relevant primary studies)
  - Case reports/case series with very small numbers (<10 cases)
  - Editorials/commentaries/opinion pieces/policy papers
  - Studies conducted exclusively during outbreaks of the specific pathogens being studied"""
}

USER_CRITERIA = None


# --- Getter Functions ---
def get_llm_providers_info():
    return SUPPORTED_LLM_PROVIDERS


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
    global USER_CRITERIA
    current_criteria_dict = USER_CRITERIA if USER_CRITERIA is not None else DEFAULT_EXAMPLE_CRITERIA
    return PICOT_TEMPLATE.format(
        population_criteria=current_criteria_dict.get("population_criteria", ""),
        intervention_criteria=current_criteria_dict.get("intervention_criteria", ""),
        comparison_criteria=current_criteria_dict.get("comparison_criteria", ""),
        outcome_criteria=current_criteria_dict.get("outcome_criteria", ""),
        time_criteria=current_criteria_dict.get("time_criteria", ""),
        other_inclusion_criteria=current_criteria_dict.get("other_inclusion_criteria", ""),
        exclusion_criteria=current_criteria_dict.get("exclusion_criteria", "")
    )


def set_user_criteria(criteria_dict):
    global USER_CRITERIA
    USER_CRITERIA = criteria_dict


def reset_to_default_criteria():
    global USER_CRITERIA
    USER_CRITERIA = DEFAULT_EXAMPLE_CRITERIA.copy()