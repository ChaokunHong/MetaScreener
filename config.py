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
    "p_include": """示例包含标准：
- 来自社区环境的一般人群（家庭、学校、工作场所、社区筛查项目）
- 包括所有年龄、性别、孕妇
- 扩展人群（具有社区代表性）：门诊患者（非因研究感染就医）、体检者、社区志愿者

提示：请具体说明目标人群的特征，如年龄范围、性别、特定条件等。""",
    "p_exclude": """示例排除标准：
- 住院患者（>48小时）
- NICU/特殊护理的新生儿
- 医护人员
- 长期护理机构居民
- 国际旅行者（<6个月前）
- 特定职业群体（兽医、动物处理者、农民等）
- 因研究感染就医的患者

提示：列出明确的排除特征，确保与包含标准不矛盾。""",
    "p_maybe": """示例"可能"情况：
- 提到社区环境但未明确说明招募方法
- 提到年龄组但不够精确（如仅说"儿童"）

提示：关注摘要中可能缺失的关键人群信息。""",
    # Intervention
    "i_include": """示例包含标准：
- 观察性研究（横断面、队列、病例对照）或具有基线AMR数据的RCT
- 无需特定干预

提示：明确说明可接受的研究类型和必要的数据要求。""",
    "i_exclude": """示例排除标准：
（未定义特定干预排除标准）

提示：如果有特定需要排除的干预类型，请在此说明。""",
    "i_maybe": """示例"可能"情况：
- 描述了数据收集但未明确说明研究设计（如，听起来像横断面研究但未明确说明）

提示：指出哪些研究设计细节需要澄清。""",
    # Comparison
    "c_include": """示例包含标准：
- 无需特定对照组

提示：如果需要特定对照组，请明确说明要求。""",
    "c_exclude": """示例排除标准：
（未定义特定对照组排除标准）

提示：说明任何不可接受的对照组类型。""",
    "c_maybe": """示例"可能"情况：
（如果不需要对照组则不适用）

提示：列出需要澄清的对照组相关信息。""",
    # Outcome
    "o_include": """示例包含标准：
- 报告WHO BPPL病原体的抗菌素耐药性（AMR）流行率（不包括结核病、淋病）

提示：具体说明需要的结果指标和测量方法。""",
    "o_exclude": """示例排除标准：
- 未报告AMR数据
- 仅关注被排除的病原体（结核病、淋病）

提示：明确指出哪些结果会导致排除。""",
    "o_maybe": """示例"可能"情况：
- 提到耐药性测试但未明确说明病原体
- 提到相关病原体但不清楚是否报告了AMR流行率

提示：指出需要在全文中确认的结果细节。""",
    # Time/Study Type
    "t_include": """示例包含标准：
- 任何发表年份
- 任何地理位置
- 原创研究文章

提示：说明时间范围和可接受的研究类型。""",
    "t_exclude": """示例排除标准：
- 系统综述、meta分析、综述文章、社论、评论、政策文件
- 病例报告/系列（<10例）
- 仅在研究病原体已知爆发期间进行的研究

提示：列出不符合要求的研究类型和时间特征。""",
    "t_maybe": """示例"可能"情况：
- 摘要未明确说明是原创研究还是综述类型

提示：指出需要确认的研究设计特征。""",
    # Other
    "other_inclusion": """其他包含标准示例：
（未定义其他特定包含标准）

提示：添加任何不属于PICOT框架的其他必要包含标准。""",
    "other_exclusion": """其他排除标准示例：
（未定义其他特定排除标准）

提示：添加任何不属于PICOT框架的其他必要排除标准。""",
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