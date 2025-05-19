import os
from dotenv import load_dotenv
from typing import Dict, List, TypedDict

load_dotenv()

# --- Global Default Prompt Settings ---
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

# --- Configuration for PDF Processing ---
TESSERACT_CMD_PATH = os.getenv("TESSERACT_CMD_PATH", None)
PDF_OCR_THRESHOLD_CHARS = int(os.getenv("PDF_OCR_THRESHOLD_CHARS", 50))

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
            {"id": "gemini-1.0-pro", "display_name": "Gemini 1.0 Pro", "type": "chat"},
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
            {"id": "claude-3-sonnet-20240229", "display_name": "Claude 3 Sonnet (Balanced Reasoning)", "type": "reasoning"},
            {"id": "claude-3-opus-20240229", "display_name": "Claude 3 Opus (Max Intelligence)", "type": "reasoning"},
            {"id": "claude-2.1", "display_name": "Claude 2.1 (Older Reasoning)", "type": "reasoning"},
        ]
    }
}

class FrameworkElement(TypedDict):
    id: str 
    name: str 

# --- NEW: Screening Criteria Frameworks Definitions (Skeleton) ---
SUPPORTED_CRITERIA_FRAMEWORKS = {
    "PICOT": {
        "display_name": "PICOT (Population, Intervention, Comparison, Outcome, Time)",
        "elements": [
            {"id": "p", "name": "Population/Patient/Problem"},
            {"id": "i", "name": "Intervention"},
            {"id": "c", "name": "Comparison"},
            {"id": "o", "name": "Outcome"},
            {"id": "t", "name": "Time / Study Type"},
            {"id": "other", "name": "Other General Criteria"}
        ],
        "default_criteria_key": "PICOT_DEFAULT",
        "template_string": """# {framework_display_name} Framework Criteria
## P (Population/Patient/Problem):
{{{p_include}}}
## I (Intervention):
{{{i_include}}}
## C (Comparison):
{{{c_include}}}
## O (Outcome):
{{{o_include}}}
## T (Time / Study Type):
{{{t_include}}}
## Other Inclusion Criteria:
{{{other_inclusion}}}
## Other Exclusion Criteria:
{{{other_exclusion}}}
"""
    },
    "SPIDER": {
        "display_name": "SPIDER (Sample, Phenomenon, Intervention, Data, Evaluation, Research, Other)",
        "elements": [
            {"id": "s", "name": "Sample"},
            {"id": "p", "name": "Phenomenon"},
            {"id": "i", "name": "Intervention"},
            {"id": "d", "name": "Data"},
            {"id": "e", "name": "Evaluation"},
            {"id": "r", "name": "Research"},
            {"id": "other", "name": "Other General Criteria"}
        ],
        "default_criteria_key": "SPIDER_DEFAULT",
        "template_string": """# {framework_display_name} Framework Criteria
## S (Sample):
{{{s_include}}}{{{s_exclude}}}{{{s_maybe}}}
## P (Phenomenon):
{{{p_include}}}{{{p_exclude}}}{{{p_maybe}}}
## I (Intervention):
{{{i_include}}}{{{i_exclude}}}{{{i_maybe}}}
## D (Data):
{{{d_include}}}{{{d_exclude}}}{{{d_maybe}}}
## E (Evaluation):
{{{e_eval_include}}}{{{e_eval_exclude}}}{{{e_eval_maybe}}}
## R (Research):
{{{r_include}}}{{{r_exclude}}}{{{r_maybe}}}
## Other Inclusion Criteria:
{{{other_inclusion}}}
## Other Exclusion Criteria:
{{{other_exclusion}}}
"""
    },
    "PICOS": {
        "display_name": "PICOS (Population, Intervention, Comparison, Outcome, Study Design)",
        "elements": [{"id": "p", "name": "Population"}, {"id": "i", "name": "Intervention"}, {"id": "c", "name": "Comparison"}, {"id": "o", "name": "Outcome"}, {"id": "s_design", "name": "Study Design"}, {"id": "other", "name": "Other General Criteria"}],
        "default_criteria_key": "PICOS_DEFAULT",
        "template_string": """# {framework_display_name} Framework Criteria
## P (Population):
{{{p_include}}}{{{p_exclude}}}{{{p_maybe}}}
## I (Intervention):
{{{i_include}}}{{{i_exclude}}}{{{i_maybe}}}
## C (Comparison):
{{{c_include}}}{{{c_exclude}}}{{{c_maybe}}}
## O (Outcome):
{{{o_include}}}{{{o_exclude}}}{{{o_maybe}}}
## S (Study Design):
{{{s_design_include}}}{{{s_design_exclude}}}{{{s_design_maybe}}}
## Other Inclusion Criteria:
{{{other_inclusion}}}
## Other Exclusion Criteria:
{{{other_exclusion}}}
"""
    },
    "PECO": {
        "display_name": "PECO (Population, Exposure, Comparison, Outcome)", 
        "elements": [{"id":"p","name":"Population"},{"id":"e_exp","name":"Exposure"},{"id":"c","name":"Comparison"},{"id":"o","name":"Outcome"},{"id":"other","name":"Other General Criteria"}], 
        "default_criteria_key": "PECO_DEFAULT", 
        "template_string": """# {framework_display_name} Framework Criteria
## P (Population):
{{{p_include}}}{{{p_exclude}}}{{{p_maybe}}}
## E (Exposure):
{{{e_exp_include}}}{{{e_exp_exclude}}}{{{e_exp_maybe}}}
## C (Comparison):
{{{c_include}}}{{{c_exclude}}}{{{c_maybe}}}
## O (Outcome):
{{{o_include}}}{{{o_exclude}}}{{{o_maybe}}}
## Other Inclusion Criteria:
{{{other_inclusion}}}
## Other Exclusion Criteria:
{{{other_exclusion}}}
"""
    },
    "PICOC": {
        "display_name": "PICOC (Population, Intervention, Comparison, Outcome, Context)", 
        "elements": [{"id":"p","name":"Population"},{"id":"i","name":"Intervention"},{"id":"c_comp","name":"Comparison"},{"id":"o","name":"Outcome"},{"id":"c_context","name":"Context"},{"id":"other","name":"Other General Criteria"}], 
        "default_criteria_key": "PICOC_DEFAULT", 
        "template_string": """# {framework_display_name} Framework Criteria
## P (Population):
{{{p_include}}}{{{p_exclude}}}{{{p_maybe}}}
## I (Intervention):
{{{i_include}}}{{{i_exclude}}}{{{i_maybe}}}
## Co (Comparison):
{{{c_comp_include}}}{{{c_comp_exclude}}}{{{c_comp_maybe}}}
## O (Outcome):
{{{o_include}}}{{{o_exclude}}}{{{o_maybe}}}
## Ct (Context):
{{{c_context_include}}}{{{c_context_exclude}}}{{{c_context_maybe}}}
## Other Inclusion Criteria:
{{{other_inclusion}}}
## Other Exclusion Criteria:
{{{other_exclusion}}}
"""
    },
    "ECLIPSE": {
        "display_name": "ECLIPSE (Expectation, Client group, Location, Impact, Professionals, SErvice)", 
        "elements": [{"id":"exp","name":"Expectation"}, {"id":"cg","name":"Client group"}, {"id":"loc","name":"Location"}, {"id":"imp","name":"Impact"}, {"id":"prof","name":"Professionals involved"}, {"id":"serv","name":"SErvice"},{"id":"other","name":"Other General Criteria"}], 
        "default_criteria_key": "ECLIPSE_DEFAULT", 
        "template_string": """# {framework_display_name} Framework Criteria
## E (Expectation):
{{{exp_include}}}{{{exp_exclude}}}{{{exp_maybe}}}
## C (Client group):
{{{cg_include}}}{{{cg_exclude}}}{{{cg_maybe}}}
## L (Location):
{{{loc_include}}}{{{loc_exclude}}}{{{loc_maybe}}}
## I (Impact):
{{{imp_include}}}{{{imp_exclude}}}{{{imp_maybe}}}
## P (Professionals involved):
{{{prof_include}}}{{{prof_exclude}}}{{{prof_maybe}}}
## SE (SErvice):
{{{serv_include}}}{{{serv_exclude}}}{{{serv_maybe}}}
## Other Inclusion Criteria:
{{{other_inclusion}}}
## Other Exclusion Criteria:
{{{other_exclusion}}}
"""
    },
    "CLIP": {
        "display_name": "CLIP (Client, Location, Intervention, Professionals)", 
        "elements": [{"id":"cl","name":"Client"},{"id":"loc","name":"Location"},{"id":"i","name":"Intervention"},{"id":"prof","name":"Professionals"},{"id":"other","name":"Other General Criteria"}], 
        "default_criteria_key": "CLIP_DEFAULT", 
        "template_string": """# {framework_display_name} Framework Criteria
## C (Client):
{{{cl_include}}}{{{cl_exclude}}}{{{cl_maybe}}}
## L (Location):
{{{loc_include}}}{{{loc_exclude}}}{{{loc_maybe}}}
## I (Intervention):
{{{i_include}}}{{{i_exclude}}}{{{i_maybe}}}
## P (Professionals):
{{{prof_include}}}{{{prof_exclude}}}{{{prof_maybe}}}
## Other Inclusion Criteria:
{{{other_inclusion}}}
## Other Exclusion Criteria:
{{{other_exclusion}}}
"""
    },
    "BeHEMoTh": {
        "display_name": "BeHEMoTh (Behaviour of interest, Health context, Exclusions, Models or Theories)", 
        "elements": [{"id":"beh","name":"Behaviour of interest"},{"id":"hc","name":"Health context"},{"id":"excl","name":"Exclusions (framework specific)"},{"id":"mt","name":"Models or Theories"},{"id":"other","name":"Other General Criteria"}], 
        "default_criteria_key": "BEHEMOTH_DEFAULT", 
        "template_string": """# {framework_display_name} Framework Criteria
## B (Behaviour of interest):
{{{beh_include}}}{{{beh_exclude}}}{{{beh_maybe}}}
## H (Health context):
{{{hc_include}}}{{{hc_exclude}}}{{{hc_maybe}}}
## E (Exclusions (framework specific)):
{{{excl_include}}}{{{excl_exclude}}}{{{excl_maybe}}}
## M/T (Models or Theories):
{{{mt_include}}}{{{mt_exclude}}}{{{mt_maybe}}}
## Other Inclusion Criteria:
{{{other_inclusion}}}
## Other Exclusion Criteria:
{{{other_exclusion}}}
"""
    }
}

# --- DEFAULT_FRAMEWORK_VALUES (Skeleton) ---
DEFAULT_FRAMEWORK_VALUES = {
    "PICOT_DEFAULT": {
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
- Age group mentioned but not precise enough, e.g., just says \"children\"

Tip: Focus on key population information that might be missing from abstracts, needed for a clear decision.""",
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
        "c_include": """Example Include Criteria:
- No specific comparison group required

Tip: If specific comparison groups are needed, clearly state requirements.""",
        "c_exclude": """Example Exclude Criteria:
(No specific comparison exclusions defined)

Tip: State any unacceptable comparison group types.""",
        "c_maybe": """Example 'Maybe' Scenarios:
(N/A if no comparison required)

Tip: Focus on key comparison details that might be missing from abstracts, needed for a clear decision (if applicable).""",
        "o_include": """Example Include Criteria:
- Reports prevalence of Antimicrobial Resistance (AMR) for specified WHO BPPL pathogens (excluding TB, Gonorrhea)

Tip: Specify required outcome measures and measurement methods.""",
        "o_exclude": """Example Exclude Criteria:
- Does not report AMR data
- Focuses only on excluded pathogens (TB, Gonorrhea)

Tip: Clearly indicate which outcomes lead to exclusion.""",
        "o_maybe": """Example 'Maybe' Scenarios:
- Mentions resistance testing but doesn\'t specify pathogens
- Mentions relevant pathogen but unclear if AMR prevalence reported

Tip: Focus on key outcome details that might be missing from abstracts, needed for a clear decision.""",
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
- Abstract doesn\'t clearly state if it\'s original research vs. review type

Tip: Focus on key study type/publication details that might be missing from abstracts, needed for a clear decision.""",
        "other_inclusion": """(No other specific inclusion criteria defined)
Tip: Add any necessary criteria.""",
        "other_exclusion": """(No other specific exclusion criteria defined)
Tip: Add any necessary criteria.""",
        "ai_system_prompt": DEFAULT_SYSTEM_PROMPT,
        "ai_output_format_instructions": DEFAULT_OUTPUT_INSTRUCTIONS
    },
    "SPIDER_DEFAULT": {
        "s_include": """Example: Qualitative studies focusing on adults (18+ years) who are primary informal caregivers (e.g., family members) for individuals with a clinical diagnosis of Alzheimer's disease, residing in a community setting.
Tip: Define your sample precisely: Who are they (age, role, specific experience)? What are their key demographic or contextual characteristics? What is the setting?""",
        "s_exclude": """Example: Studies focusing on paid/formal health professionals as caregivers, caregivers of patients in long-term institutional settings (e.g., nursing homes), or samples where the caregiving context for dementia is not the primary or explicit focus.
Tip: What sample characteristics or settings would make a study irrelevant?""",
        "s_maybe": """Example: Abstract mentions \"caregivers of dementia patients\" but doesn\'t specify if they are informal/family caregivers, the type of dementia, or if the setting is community-based versus institutional.
Tip: What specific details about the sample, if missing from an abstract, would be too vague?""",
        "pi_include": """Example: The phenomenon of interest is the lived experience of caregiver burden, emotional impact of caregiving, coping strategies employed by caregivers, or perceived support needs.
Tip: Clearly articulate the specific experiences, views, social processes, or cultural contexts you are aiming to understand or explore.""",
        "pi_exclude": """Example: Studies that primarily measure the prevalence or severity of caregiver burden using only quantitative scales without in-depth qualitative exploration. Studies focused on the efficacy of interventions for caregivers rather than their subjective experiences.
Tip: What related phenomena are you *not* interested in?""",
        "pi_maybe": """Example: Abstract mentions \"caregiver stress\" but doesn\'t clarify if it explores the qualitative depth of these experiences.
Tip: When is the description of the phenomenon in an abstract too superficial?""",
        "d_include": """Example: Explicitly stated qualitative study designs such as phenomenology, ethnography, grounded theory, case study, narrative inquiry, descriptive qualitative studies, qualitative case studies.
Tip: List the specific qualitative methodologies or approaches you are targeting.""",
        "d_exclude": """Example: Purely quantitative designs (e.g., RCTs, surveys). Systematic reviews of quantitative studies, meta-analyses, purely theoretical papers.
Tip: Clearly list study designs that are not qualitative.""",
        "d_maybe": """Example: Abstract states data was collected via \'interviews\' or \'focus groups\' but does not explicitly name the qualitative study design.
Tip: What information about study design would be insufficient?""",
        "e_eval_include": """Example: Evaluation of themes, patterns, or categories emerging from the qualitative data regarding the phenomenon of interest.
Tip: How are the qualitative findings/phenomena being interpreted or evaluated?""",
        "e_eval_exclude": """Example: Studies where evaluation is purely statistical or qualitative data is used merely anecdotally.
Tip: What kind of evaluation would make the study not fit?""",
        "e_eval_maybe": """Example: Abstract presents some qualitative findings but the depth or method of evaluation/analysis is unclear.
Tip: What evaluation details would be too vague?""",
        "r_include": """Example: Primary qualitative research articles. Mixed-methods studies where the qualitative component is significant and directly addresses the research question.
Tip: Specify if only primary qualitative studies are included.""",
        "r_exclude": """Example: Dissertations (unless published as peer-reviewed articles), conference abstracts without full-text.
Tip: List types of publications or research outputs to exclude.""",
        "r_maybe": """Example: Abstract is from a conference proceeding and it\'s unclear if a full peer-reviewed article exists.
Tip: When is the research type or publication status unclear?""",
        "other_inclusion": "Example: Studies published in English language.\nTip: Any other general inclusion criteria.",
        "other_exclusion": "Example: Studies published before the year 2000.\nTip: Any other general exclusion criteria.",
        "ai_system_prompt": DEFAULT_SYSTEM_PROMPT,
        "ai_output_format_instructions": DEFAULT_OUTPUT_INSTRUCTIONS
    },
    "PICOS_DEFAULT": {
        "p_include": """Example Include Criteria:
- Adults (≥18 years) with diagnosed major depressive disorder (MDD)
- Children and adolescents (5-17 years) with attention deficit hyperactivity disorder (ADHD)
- Patients with type 2 diabetes mellitus and HbA1c ≥7.0%
- Individuals with chronic low back pain (>12 weeks duration)
- Community-dwelling elderly (≥65 years) at risk of falls
- Pregnant women in their first trimester with morning sickness

Tip: Define your target population precisely - include age ranges, diagnostic criteria, disease severity, and relevant demographic characteristics.""",
        "p_exclude": """Example Exclude Criteria:
- Patients with severe psychiatric comorbidities
- Individuals with cognitive impairment preventing informed consent
- Terminal illness with life expectancy <6 months
- History of adverse reactions to similar interventions
- Participation in other clinical trials within past 30 days
- Unstable medical conditions requiring urgent care

Tip: Clearly specify which population characteristics would make participation inappropriate or potentially harmful.""",
        "p_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "adults" without specifying age range
- Diagnostic criteria or disease severity not clearly stated
- Unclear if comorbidities were considered
- Population described as "patients" without specific characteristics
- Pregnancy status not specified when relevant
- Baseline functional status not described

Tip: Note what missing population information would require clarification from full text.""",
        "i_include": """Example Include Criteria:
- Structured cognitive behavioral therapy (12 weekly sessions)
- Novel pharmacological intervention with specified dosing regimen
- Supervised exercise program (3 sessions/week, 60 minutes each)
- Digital health intervention with daily monitoring
- Mindfulness-based stress reduction program
- Dietary intervention with registered dietitian support

Tip: Describe intervention components, duration, frequency, and delivery method in detail.""",
        "i_exclude": """Example Exclude Criteria:
- Non-standardized or poorly described interventions
- Interventions requiring unavailable specialized equipment
- Experimental procedures without preliminary safety data
- Complementary therapies without evidence base
- Single session or very brief interventions
- Interventions without clear protocols

Tip: Exclude interventions that lack standardization or feasibility in your context.""",
        "i_maybe": """Example 'Maybe' Scenarios:
- Intervention described as "standard care" without specifics
- Duration or intensity not clearly specified
- Unclear delivery method (individual vs. group)
- Provider qualifications not mentioned
- Adherence monitoring process not described
- Intervention components not fully detailed

Tip: Identify when intervention details need clarification from full text.""",
        "c_include": """Example Include Criteria:
- Standard care or treatment as usual
- Placebo-controlled comparisons
- Active control with established intervention
- Waitlist control groups
- Attention-matched control conditions
- Dose-response comparisons

Tip: Define acceptable comparison groups that will provide meaningful evidence.""",
        "c_exclude": """Example Exclude Criteria:
- No control or comparison group
- Historically controlled studies without contemporary comparison
- Comparisons with obsolete treatments
- Inadequately matched control groups
- Contaminated control conditions
- Ethically inappropriate comparisons

Tip: Specify which comparison designs would not provide valid evidence.""",
        "c_maybe": """Example 'Maybe' Scenarios:
- Control condition described vaguely
- Matching procedures not detailed
- Unclear if controls received any intervention
- Cross-over timing not specified
- Contamination prevention not described
- Baseline comparability not addressed

Tip: Note what comparison details need clarification from full text.""",
        "o_include": """Example Include Criteria:
- Primary outcomes measured with validated instruments
- Patient-reported outcomes using standardized measures
- Clinically meaningful endpoints
- Objective physiological measurements
- Quality of life assessments
- Cost-effectiveness analyses

Tip: Specify required outcomes and their measurement methods.""",
        "o_exclude": """Example Exclude Criteria:
- Non-validated outcome measures
- Surrogate endpoints without clinical relevance
- Subjective outcomes without standardization
- Incomplete outcome reporting
- Inappropriate timing of measurements
- Outcomes susceptible to significant bias

Tip: Exclude outcomes that won't provide reliable evidence.""",
        "o_maybe": """Example 'Maybe' Scenarios:
- Outcome measures not fully described
- Timing of assessments unclear
- Validation status of measures uncertain
- Multiple outcomes without specified primary
- Missing important secondary outcomes
- Unclear clinical significance thresholds

Tip: Identify when outcome details need clarification from full text.""",
        "s_design_include": """Example Include Criteria:
- Randomized controlled trials (RCTs)
- Cluster randomized trials
- Pragmatic clinical trials
- Factorial design studies
- Adaptive trial designs
- Well-designed prospective cohort studies

Tip: Define acceptable study designs that will provide appropriate level of evidence.""",
        "s_design_exclude": """Example Exclude Criteria:
- Case reports or case series
- Retrospective studies
- Pilot studies without power calculations
- Non-peer reviewed studies
- Studies with major methodological flaws
- Qualitative studies

Tip: Specify which study designs would not meet your evidence requirements.""",
        "s_design_maybe": """Example 'Maybe' Scenarios:
- Study design not explicitly stated
- Randomization process not described
- Sample size justification unclear
- Blinding procedures not detailed
- Follow-up duration not specified
- Analysis plan not fully described

Tip: Note what study design details need clarification from full text.""",
        "other_inclusion": """Example Include Criteria:
- English language publications
- Peer-reviewed journal articles
- Studies with appropriate ethical approval
- Adequate sample size based on power calculations
- Clear reporting of statistical methods
- Studies following CONSORT guidelines""",
        "other_exclusion": """Example Exclude Criteria:
- Conference abstracts without full publication
- Studies with significant conflicts of interest
- Publications before 2000
- Studies with >30% dropout rate
- Interim analyses without final results
- Duplicate publications of same data""",
        "ai_system_prompt": DEFAULT_SYSTEM_PROMPT,
        "ai_output_format_instructions": DEFAULT_OUTPUT_INSTRUCTIONS
    },
    "PECO_DEFAULT": {
        "p_include": """Example Include Criteria:
- Adults (≥18 years) living in urban areas for ≥10 years with no pre-existing respiratory conditions
- Children (5-17 years) attending schools within 500m of air quality monitoring stations
- Non-smoking individuals with normal baseline pulmonary function tests
- Residents of communities adjacent to industrial zones or high-traffic areas

Tip: Define population characteristics clearly - specify age groups, residence duration, baseline health status, and geographic context.""",
        "p_exclude": """Example Exclude Criteria:
- Current or former smokers (>100 cigarettes lifetime)
- Individuals with pre-existing asthma, COPD, or other chronic respiratory conditions
- Occupational exposure to respiratory hazards (e.g., miners, chemical industry workers)
- Recent relocations (<2 years in current residence)
- Pregnant women or immunocompromised individuals

Tip: Clearly identify characteristics that would confound exposure-outcome relationships.""",
        "p_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "healthy adults" but does not specify smoking status
- Residential history duration not clearly stated
- Unclear if baseline respiratory assessment was conducted
- Mentions "urban residents" without specifying proximity to exposure sources

Tip: Identify key population information that if missing would make inclusion/exclusion decisions difficult.""",
        "e_exp_include": """Example Include Criteria:
- Ambient air pollution exposure (PM2.5, PM10, NO2, O3) measured by fixed monitoring stations
- Occupational exposure to specific chemicals with documented exposure levels
- Residential proximity to pollution sources (≤1km from highways, industrial facilities)
- Biomarker-confirmed exposure (e.g., blood lead levels, urinary metabolites)
- Minimum exposure duration of 6 months

Tip: Specify exposure type, measurement method, intensity thresholds, and duration requirements.""",
        "e_exp_exclude": """Example Exclude Criteria:
- Self-reported exposure without objective measurement
- Short-term or acute exposures (<1 month)
- Studies using modeled exposure data without validation
- Indoor air pollution only without assessment of outdoor exposures
- Exposure levels below regulatory thresholds or reference values

Tip: Exclude poorly characterized exposures or those unlikely to produce the outcomes of interest.""",
        "e_exp_maybe": """Example 'Maybe' Scenarios:
- Exposure described only as "air pollution" without specifying pollutants
- Monitoring method mentioned but frequency/duration unclear
- Abstract states "exposed communities" without quantitative measurements
- Unclear if exposure was continuous or intermittent
- Mentions "proximity to sources" without distance specifications

Tip: Note when exposure assessment details are insufficient to determine eligibility.""",
        "c_include": """Example Include Criteria:
- Comparison with individuals in areas with documented low exposure levels
- Same population before exposure (temporal comparison)
- Matched controls from similar socioeconomic and geographic settings without the exposure
- Dose-response assessment comparing multiple exposure levels
- Reference groups meeting WHO air quality standards

Tip: Define appropriate comparison groups that isolate the exposure effect.""",
        "c_exclude": """Example Exclude Criteria:
- No comparison or reference group included
- Comparison groups with significant confounding exposures
- Poorly matched control groups (different baseline health status, socioeconomic factors)
- Historical controls from different time periods without accounting for temporal trends
- Reference groups with insufficient exposure contrast

Tip: Exclude studies with inadequate comparison groups that could bias findings.""",
        "c_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "compared to controls" without describing control characteristics
- Unclear if control areas are truly unexposed or just less exposed
- Matching criteria for cases and controls not specified
- Abstract doesn't clarify if socioeconomic factors were considered in group selection
- Reference levels not quantified

Tip: Flag when comparison methodology is inadequately described.""",
        "o_include": """Example Include Criteria:
- Physician-diagnosed respiratory conditions (asthma, bronchitis, COPD)
- Objective lung function measurements (FEV1, FVC, PEF, DLCO)
- Validated biomarkers of respiratory inflammation or damage
- Frequency of respiratory symptoms documented with validated questionnaires
- Healthcare utilization for respiratory conditions (ED visits, hospitalizations)
- Minimum follow-up period of 12 months for outcome assessment

Tip: Specify required outcomes, diagnostic criteria, measurement methods, and timing.""",
        "o_exclude": """Example Exclude Criteria:
- Self-reported symptoms without clinical confirmation
- Non-specific health outcomes not clearly linked to respiratory system
- Single timepoint assessments without baseline measurements
- Outcomes with inadequate statistical adjustment for confounders
- Surrogate endpoints without validated correlation to clinical outcomes

Tip: Exclude studies with subjective or poorly defined outcome measures.""",
        "o_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "respiratory effects" without specifying measurements
- Method of diagnosis or assessment not clearly stated
- Unclear if outcome was primary or secondary endpoint
- Follow-up duration not specified
- Outcome attribution method (to exposure) not described

Tip: Identify when critical outcome information is missing that prevents clear decisions.""",
        "other_inclusion": """Example Include Criteria:
- Study designs: cohort studies, case-control studies, cross-sectional studies with appropriate analysis
- Publication date: 2000 or later
- Peer-reviewed publications with full methodology description
- Sample size with adequate statistical power (defined by outcome)
- Studies with appropriate confounder adjustment (e.g., socioeconomic status, age, comorbidities)

Tip: Consider methodological quality requirements beyond the PECO framework.""",
        "other_exclusion": """Example Exclude Criteria:
- Case reports, narrative reviews, opinion pieces
- Studies without ethics approval documentation
- Conference abstracts without subsequent publication
- Languages other than English, Spanish, French
- Duplicate publications of the same dataset

Tip: Consider practical limitations and quality standards for exclusion.""",
        "ai_system_prompt": DEFAULT_SYSTEM_PROMPT, 
        "ai_output_format_instructions": DEFAULT_OUTPUT_INSTRUCTIONS
    },
    "PICOC_DEFAULT": {
        "p_include": "Example Include Criteria:\n- K-12 students enrolled in public schools.\nTip: 指定教育环境与年级段。", 
        "p_exclude": "Example Exclude Criteria:\n- Homeschooled or special-education-only populations。", 
        "p_maybe": "Example 'Maybe' Scenarios:\n- Abstract 未明确公立或私立学校。",
        "i_include": "Example Include Criteria:\n- Tablet-based mathematics learning apps used ≥4 weeks。", 
        "i_exclude": "Example Exclude Criteria:\n- 传统纸质教材无数字成分。", 
        "i_maybe": "Example 'Maybe' Scenarios:\n- 仅提\"digital resources\" 未指明应用类型。",
        "c_comp_include": "Example Include Criteria:\n- Regular classroom instruction without digital support。", 
        "c_comp_exclude": "Example Exclude Criteria:\n- 对照组亦使用其他电子学习工具。", 
        "c_comp_maybe": "Example 'Maybe' Scenarios:\n- 对照方法描述不足。",
        "o_include": "Example Include Criteria:\n- Standardised math test scores at semester end。", 
        "o_exclude": "Example Exclude Criteria:\n- 仅报告学生满意度或出勤率。", 
        "o_maybe": "Example 'Maybe' Scenarios:\n- 结果仅说\"improved performance\" 无量化指标。",
        "c_context_include": "Example Include Criteria:\n- Classroom setting during regular school hours in OECD countries。", 
        "c_context_exclude": "Example Exclude Criteria:\n- After-school tutoring centres。", 
        "c_context_maybe": "Example 'Maybe' Scenarios:\n- Abstract 未提地理或教学场景。",
        "other_inclusion": "Example: Articles in English or Spanish。", "other_exclusion": "Example: Published before 1990。",
        "ai_system_prompt": DEFAULT_SYSTEM_PROMPT, "ai_output_format_instructions": DEFAULT_OUTPUT_INSTRUCTIONS
    },
    "ECLIPSE_DEFAULT": {
        "exp_include": """Example Include Criteria:
- Information needed to assess effectiveness of telehealth interventions for chronic disease management
- Data on patient and provider satisfaction with integrated electronic health record systems
- Evidence for cost-effectiveness of community health worker programs in rural settings
- Assessments of waiting time reductions following service redesign initiatives
- Evaluations of service accessibility improvements for underserved populations

Tip: Clearly state what knowledge or information need drives this review - what decision or assessment will the findings inform?""",
        "exp_exclude": """Example Exclude Criteria:
- Purely technical evaluations of healthcare software without service delivery assessment
- Studies focused only on clinical outcomes without addressing service quality aspects
- Financial analyses without patient-centered outcomes
- Research focused primarily on clinical efficacy rather than service delivery
- Implementation studies without evaluation components

Tip: Define what types of information would not address your core service evaluation question.""",
        "exp_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "evaluation" but doesn't specify what aspects were assessed
- Unclear if patient perspectives were included alongside clinical outcomes
- Study described as "quality improvement" without specifying measures
- Mentions "effectiveness" without clarifying if this includes service delivery components
- Not clear if economic analyses include service-level metrics

Tip: Identify when expectation/information need is ambiguously described.""",
        "cg_include": """Example Include Criteria:
- Adults (≥18 years) with type 2 diabetes managed in primary care settings
- Children and adolescents (2-17 years) receiving developmental screening services
- Elderly patients (≥65 years) using home care services following hospital discharge
- Pregnant women attending prenatal care in low-resource settings
- Individuals with severe mental illness engaged with community mental health services

Tip: Define the specific client/patient population whose service experience is being evaluated.""",
        "cg_exclude": """Example Exclude Criteria:
- Acute care/emergency patients (unless service specifically targets this group)
- Individuals without diagnosed conditions in screening programs
- Healthcare providers as primary study participants (unless evaluating provider experience)
- Healthy volunteers in simulated service scenarios
- Studies where patient characteristics are not clearly defined

Tip: Specify which client groups would not provide relevant insights for your service question.""",
        "cg_maybe": """Example 'Maybe' Scenarios:
- Abstract references "patients" without specifying age, condition, or care context
- Mentions "service users" without describing their characteristics
- Unclear if study includes appropriate mix of demographics representative of service
- Doesn't specify disease severity or stage for condition-specific services
- Unclear if caregivers/family members are included alongside patients

Tip: Note when client group description lacks critical details for relevance assessment.""",
        "loc_include": """Example Include Criteria:
- Primary healthcare centers in rural and underserved communities
- Outpatient specialty clinics within integrated health systems
- Telehealth services delivered to patients' homes
- Community-based health services in defined geographic regions
- Health services in low and middle-income countries matching target implementation context

Tip: Specify the physical, organizational, or virtual location where services are delivered.""",
        "loc_exclude": """Example Exclude Criteria:
- Tertiary or quaternary specialized centers (if focusing on primary care)
- Healthcare settings in healthcare systems substantially different from target implementation context
- Experimental facilities not operating under real-world conditions
- Inpatient settings (if reviewing community-based interventions)
- Single-site studies with unique characteristics limiting generalizability

Tip: Exclude locations that don't match your target service delivery environment.""",
        "loc_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "clinical setting" without specifying facility type
- Unclear if "community setting" refers to homes, clinics, or other locations
- Location described only as "urban" or "rural" without further details
- Not specified if virtual services include synchronous or asynchronous components
- Geographic region mentioned but healthcare system characteristics not described

Tip: Identify when location is too vaguely described to determine relevance.""",
        "imp_include": """Example Include Criteria:
- Measures of service accessibility (appointment waiting times, service uptake rates)
- Patient-reported experience measures using validated instruments
- System efficiency metrics (throughput, resource utilization, cost per encounter)
- Health equity outcomes (service distribution across population segments)
- Implementation outcomes (adoption rates, fidelity, sustainability)
- Clinical outcome improvements directly attributable to service features

Tip: Define what specific impacts or outcomes would indicate successful service delivery.""",
        "imp_exclude": """Example Exclude Criteria:
- Clinical outcomes without connection to service quality or delivery
- Findings without statistical significance or meaningful effect sizes
- Process measures without patient-centered outcomes
- Short-term impacts (<3 months) without assessment of sustainability
- Outcomes not aligned with stated service objectives
- Impacts measured with non-validated instruments

Tip: Specify which impacts would not provide meaningful evidence for your service question.""",
        "imp_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "improved outcomes" without specifying metrics
- Unclear if reported benefits are clinically or practically significant
- Mentions "evaluation" but doesn't list specific measures
- Time frame for impact assessment not specified
- Not clear whether outcomes are directly attributable to service characteristics
- Mixed results reported without detail on specific components

Tip: Note when impact is described too generally to assess relevance.""",
        "prof_include": """Example Include Criteria:
- Multidisciplinary primary care teams including physicians, nurses, and allied health professionals
- Community health workers and lay health advisors in underserved settings
- Specialized nurse practitioners delivering targeted chronic disease management
- Mental health professionals delivering integrated behavioral services
- Pharmacists involved in medication management services
- Care coordinators managing transitions between service settings

Tip: Specify which professional groups should be involved in service delivery.""",
        "prof_exclude": """Example Exclude Criteria:
- Services delivered exclusively by professionals outside target implementation workforce
- Non-clinical administrative staff without direct patient interaction
- Professional groups without relevant training for specific service
- Studies where professional roles are not clearly defined
- Experimental roles not sustainable in routine practice settings

Tip: Exclude professional configurations that wouldn't be feasible or relevant.""",
        "prof_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "healthcare providers" without specifying professions
- Unclear if team composition matches implementation context
- Not specified whether providers received specialized training
- Doesn't address supervision structure for support staff
- No mention of staff-to-client ratios for group interventions
- Professional experience level not specified when relevant to complex interventions
- Inter-professional communication processes not described for team approaches

Tip: Note when professional information lacks critical details for implementation assessment.""",
        "serv_include": """Example Include Criteria:
- Telemedicine consultations for chronic disease management
- Group-based diabetes self-management education programs
- Stepped care models for mental health service delivery
- Navigator programs for cancer screening and treatment
- Integrated electronic health record systems enhancing care coordination
- Mobile health clinics serving remote populations
- Community pharmacy-based medication review services

Tip: Describe the specific service model, design, or intervention being evaluated.""",
        "serv_exclude": """Example Exclude Criteria:
- One-time or short-term interventions without service system integration
- Purely clinical interventions without service delivery components
- Services requiring resources unavailable in implementation context
- Outdated service models superseded by current standards
- Pilot programs without sustainability assessment
- Services focused solely on education without care delivery components

Tip: Exclude service configurations that aren't feasible or relevant to your context.""",
        "serv_maybe": """Example 'Maybe' Scenarios:
- Abstract describes service as "innovative" without specific components
- Refers to "standard care" without defining what this includes
- Unclear if service is standalone or integrated within broader system
- Duration or intensity of service not specified
- Not clear which specific components differentiate the service from alternatives
- Mentions "technology-enabled" without specifying technologies used

Tip: Note when service description lacks critical details needed for assessment.""",
        "other_inclusion": """Example Include Criteria:
- Study designs: program evaluations, implementation studies, health services research, quality improvement reports
- Publication date: 2015 or later to reflect current service delivery contexts
- Studies with minimum 6-month follow-up to assess sustainability
- Mixed-methods studies including both quantitative outcomes and qualitative experience
- Economic analyses alongside service evaluation
- Papers with detailed description of service model implementation

Tip: Consider additional methodological or practical criteria important for review quality.""",
        "other_exclusion": """Example Exclude Criteria:
- Abstracts, protocols, and conference presentations without full reports
- Opinion pieces and narrative reviews without empirical data
- Studies without ethics approval where applicable
- Publications with conflicts of interest that may bias findings
- Studies with inadequate methodological description to assess quality
- Feasibility studies without implementation outcomes

Tip: Specify additional exclusion criteria based on methodological or reporting standards.""",
        "ai_system_prompt": DEFAULT_SYSTEM_PROMPT, 
        "ai_output_format_instructions": DEFAULT_OUTPUT_INSTRUCTIONS
    },
    "CLIP_DEFAULT": {
        "cl_include": """Example Include Criteria:
- Adults (≥18 years) with chronic lower back pain (>12 weeks duration)
- Children (5-17 years) with confirmed diagnosis of autism spectrum disorder
- Elderly patients (≥65 years) at risk of falls based on validated screening tools
- Individuals with mild to moderate depression (PHQ-9 score 10-19)
- Patients undergoing rehabilitation following knee or hip replacement
- Pregnant women in third trimester experiencing pelvic girdle pain

Tip: Define your client population precisely - specify age ranges, diagnosis criteria, condition severity, and relevant demographics.""",
        "cl_exclude": """Example Exclude Criteria:
- Acute pain (<4 weeks duration) or post-surgical pain
- Severe psychiatric conditions requiring inpatient care
- Cognitive impairment preventing active participation in intervention
- Terminal illness with life expectancy <6 months
- Specific contraindications to physical interventions (e.g., recent fracture, acute inflammation)
- Concurrent participation in other similar interventions

Tip: Clearly state which client characteristics would make the intervention inappropriate or potentially harmful.""",
        "cl_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "back pain" without specifying acute or chronic
- Refers to "depression" without indicating severity or diagnostic criteria
- Doesn't clarify if pediatric participants are accompanied by caregivers
- Unclear if "elderly" refers to specific age threshold
- Doesn't specify if diagnosis is clinically confirmed or self-reported
- Comorbidities or medication use not addressed

Tip: Identify what missing client information would make inclusion decisions difficult.""",
        "loc_include": """Example Include Criteria:
- Outpatient physiotherapy or rehabilitation clinics
- Community health centers in urban and suburban settings
- Primary care facilities offering integrated services
- Home-based intervention delivery with professional supervision
- School-based therapy services for pediatric populations
- Telehealth delivery to client's residence
- Group settings within community facilities

Tip: Specify where the intervention is delivered - consider physical settings, organizational contexts, and accessibility factors.""",
        "loc_exclude": """Example Exclude Criteria:
- Acute hospital inpatient settings
- Intensive care or specialized units
- Research laboratories not representing typical practice settings
- Settings requiring specialized equipment unavailable in implementation context
- Remote locations without adequate supervision capabilities
- Facilities without privacy provisions for sensitive interventions

Tip: Exclude locations that don't represent your intended implementation setting or lack necessary features.""",
        "loc_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "clinical setting" without specifying type
- Unclear if "community-based" refers to homes, centers, or other locations
- Doesn't specify if telehealth includes synchronous or asynchronous components
- Environment modifications or special equipment needs not described
- No indication if setting allows appropriate duration and frequency of intervention
- Urban/rural context not specified when relevant to accessibility

Tip: Note when setting information lacks sufficient detail for relevance assessment.""",
        "i_include": """Example Include Criteria:
- Manual therapy combined with graded exercise program (minimum 6 sessions)
- Cognitive-behavioral therapy for pain management (8-12 weekly sessions)
- Group-based physical activity interventions with social support components
- Technology-assisted home exercise programs with remote monitoring
- Multi-component falls prevention programs including strength and balance training
- Sensory integration therapy for children with processing disorders
- Mindfulness-based stress reduction following standardized protocols

Tip: Describe intervention components, delivery format, intensity, duration, and theoretical framework.""",
        "i_exclude": """Example Exclude Criteria:
- Passive modalities only (e.g., heat, TENS) without active components
- Surgical or invasive procedures
- Pharmacological interventions as primary treatment
- Single-session or very brief interventions (<3 sessions)
- Experimental approaches without preliminary efficacy evidence
- Interventions requiring highly specialized equipment unavailable in target settings
- Non-standardized approaches without clear protocols

Tip: Exclude interventions that don't match your practice focus or lack feasibility.""",
        "i_maybe": """Example 'Maybe' Scenarios:
- Abstract describes intervention only as "physical therapy" without components
- Duration or frequency of sessions not specified
- Unclear if intervention is individual or group-based
- Mentions "standard care" without defining components
- Doesn't specify who delivers which components of multi-modal intervention
- Level of tailoring or personalization not described
- Training requirements for providers not addressed

Tip: Identify when intervention details are insufficient for implementation assessment.""",
        "prof_include": """Example Include Criteria:
- Licensed physiotherapists/physical therapists with minimum 2 years experience
- Occupational therapists with specialized training in sensory integration
- Clinical psychologists certified in cognitive-behavioral therapy
- Multi-disciplinary teams including rehabilitation specialists and pain physicians
- Advanced practice nurses with geriatric specialty certification
- Certified exercise physiologists for physical activity interventions
- Speech-language pathologists for communication interventions

Tip: Specify required professional qualifications, training, experience levels, and team composition.""",
        "prof_exclude": """Example Exclude Criteria:
- Providers without formal certification in required techniques
- Research staff without clinical qualifications
- Students or trainees as primary intervention providers (unless specifically studying training outcomes)
- Professionals outside their scope of practice for specific techniques
- Insufficient staffing ratios for safe intervention delivery
- Providers without regular clinical supervision or quality monitoring

Tip: Exclude professional arrangements that don't meet quality or safety standards.""",
        "prof_maybe": """Example 'Maybe' Scenarios:
- Abstract refers to "clinicians" without specifying disciplines
- Training or certification requirements not mentioned
- Unclear if specialists or generalists deliver the intervention
- Doesn't address supervision structure for support staff
- No mention of staff-to-client ratios for group interventions
- Professional experience level not specified when relevant to complex interventions
- Inter-professional communication processes not described for team approaches

Tip: Note when professional information lacks critical details for implementation assessment.""",
        "other_inclusion": """Example Include Criteria:
- Studies reporting clinical outcomes using validated measurement tools
- Minimum follow-up period of 3 months to assess sustainability
- Interventions with reported adherence/compliance data
- Studies including cost-effectiveness or resource utilization measures
- Patient satisfaction or experience measures alongside clinical outcomes
- Clear description of intervention fidelity monitoring
- Studies with adequate sample size based on power calculations

Tip: Consider additional methodological criteria important for practice implementation.""",
        "other_exclusion": """Example Exclude Criteria:
- Case studies or series with fewer than 10 participants
- Studies without appropriate comparison groups
- Feasibility studies without efficacy outcomes
- Interventions without manualization or standardization
- Studies with >30% dropout without intention-to-treat analysis
- Outcomes measured only by non-blinded assessors
- Reports with inadequate statistical analysis description

Tip: Specify additional exclusion criteria based on methodological quality standards.""",
        "ai_system_prompt": DEFAULT_SYSTEM_PROMPT, 
        "ai_output_format_instructions": DEFAULT_OUTPUT_INSTRUCTIONS
    },
    "BEHEMOTH_DEFAULT": {
        "beh_include": """Example Include Criteria:
- Adherence to medication regimens in chronic disease management
- Health-promoting physical activity behavior (≥150 minutes moderate activity weekly)
- Self-management behaviors for conditions like diabetes or asthma
- Healthcare seeking behaviors including screening attendance
- Dietary behaviors supporting cardiovascular health
- Preventive behaviors such as vaccine acceptance
- Addiction-related behaviors including smoking cessation

Tip: Clearly define the specific health behavior of interest - what actions or patterns are being studied?""",
        "beh_exclude": """Example Exclude Criteria:
- Physiological responses without behavioral components
- Clinical outcomes not linked to specific behaviors
- Knowledge or attitude changes without behavioral measures
- Intentions to change behavior without actual behavior assessment
- One-time actions versus sustained behavior patterns
- Behaviors not directly related to health outcomes
- Behavioral measures without validated assessment tools

Tip: Specify which behaviors or non-behavioral elements would be outside your focus.""",
        "beh_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "lifestyle changes" without specifying behaviors
- Describes "self-care" without defining component behaviors
- Doesn't specify how behaviors were measured or over what timeframe
- Unclear if behavior is primary focus or secondary outcome
- Doesn't distinguish between behavior initiation and maintenance
- Uses non-standard definitions of behavior frequency or intensity
- Doesn't clarify if behavior was self-reported or objectively measured

Tip: Identify when behavioral description lacks specificity needed for inclusion decisions.""",
        "hc_include": """Example Include Criteria:
- Primary care settings implementing chronic disease management
- Public health initiatives targeting population health behaviors
- Mental health contexts addressing health behavior change
- Community health programs in defined geographic areas
- School-based health promotion initiatives
- Workplace wellness programs with behavioral components
- Digital health contexts supporting behavior change

Tip: Define the health context where the behavior occurs - clinical settings, public health programs, or specific domains.""",
        "hc_exclude": """Example Exclude Criteria:
- Non-health sectors without explicit health focus (e.g., general education)
- Laboratory settings without real-world implementation components
- Hypothetical scenarios without actual implementation
- Historical contexts not relevant to current practice
- Health systems fundamentally different from implementation target
- Single-site programs with unique characteristics limiting generalizability
- Contexts without defined health outcomes or goals

Tip: Exclude contexts that don't represent your target implementation setting.""",
        "hc_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "healthcare setting" without specifying type
- Doesn't clarify if program is integrated within existing systems
- Unclear organizational level (individual, group, community, policy)
- Setting described as "community-based" without further detail
- Doesn't specify urban/rural context when relevant
- Cultural context not addressed when potentially important
- Doesn't clarify if digital/telehealth components are included

Tip: Note when contextual information is too vague for relevance assessment.""",
        "excl_include": """Example Include Criteria:
- Studies explicitly identifying barriers to behavior change
- Research examining factors hindering intervention implementation
- Analysis of factors contributing to intervention non-adherence
- Identification of population subgroups not responding to interventions
- Studies addressing equity issues in behavior change access
- Research on contextual limitations of theoretical approaches
- Examination of challenges in theory operationalization

Tip: Specify what exclusionary factors or limitations should be addressed - what prevents behavior change or theory application?""",
        "excl_exclude": """Example Exclude Criteria:
- Studies not addressing implementation challenges
- Research focusing only on facilitators without addressing barriers
- Theoretical papers without empirical barrier identification
- Studies mentioning limitations only as afterthoughts
- Research not considering equity or access issues when relevant
- Intervention studies without process evaluation components
- Studies not examining reasons for non-response or dropout

Tip: Define what absence of exclusionary factor analysis would make a study irrelevant.""",
        "excl_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions "challenges" without specifying nature
- Unclear if barriers are systematically assessed or incidentally noted
- Doesn't specify if barriers are theoretical or empirically identified
- Mentions "lessons learned" without clear focus on limitations
- Not clear if exclusionary factors are addressed at individual or system level
- Doesn't clarify if equity dimensions are considered
- Mentions "mixed results" without exploring reasons for variation

Tip: Identify when exclusionary factor analysis is ambiguously described.""",
        "mt_include": """Example Include Criteria:
- Explicit use of Social Cognitive Theory for behavioral intervention design
- Health Belief Model application in preventive behavior programs
- Transtheoretical Model stages of change to tailor interventions
- Self-Determination Theory for motivation enhancement strategies
- Ecological models addressing multiple levels of behavioral influence
- Behavior change theories with clear operationalization of constructs
- Implementation science frameworks guiding program design
- Comparison of multiple theoretical approaches within intervention

Tip: Specify which behavior change models or theories should be explicitly applied or tested.""",
        "mt_exclude": """Example Exclude Criteria:
- Atheoretical approaches without conceptual framework
- Superficial mention of theory without meaningful application
- Outdated theoretical approaches superseded by current understanding
- Theories not appropriate for target behavior or population
- Models without empirical validation in similar contexts
- Theories addressing only one level of a multi-level problem
- Conceptual frameworks without clear behavior change mechanisms
- Theory cited post-hoc rather than informing design

Tip: Define what theoretical weaknesses or absences would make a study irrelevant.""",
        "mt_maybe": """Example 'Maybe' Scenarios:
- Abstract mentions being "theory-based" without naming theories
- Names a theory but doesn't describe how constructs were operationalized
- Unclear if theory guided intervention design or only evaluation
- Multiple theories mentioned without integration explanation
- Doesn't clarify if theory was adapted for population or context
- Theory components selectively applied without rationale
- Mentions "conceptual framework" without specifics
- No information on how theory informed specific intervention components

Tip: Note when theoretical information is insufficient for relevance assessment.""",
        "other_inclusion": """Example Include Criteria:
- Studies with clear reporting of theoretical construct measurement
- Research explicitly linking theory to intervention components
- Studies including both process and outcome evaluation
- Research designs appropriate for theory testing (e.g., mediation analysis)
- Detailed intervention description allowing replication
- Studies with appropriate timeframes for behavior change processes
- Publications with thorough description of context and population

Tip: Consider additional methodological criteria important for theory-based review.""",
        "other_exclusion": """Example Exclude Criteria:
- Studies with major methodological limitations undermining conclusions
- Sample sizes inadequate for proposed analyses
- Incomplete reporting of intervention components
- Selective outcome reporting biasing theory evaluation
- Invalid measures of theoretical constructs
- Timeframes too short for meaningful behavior change assessment
- Significant confounders not addressed in design or analysis

Tip: Specify additional exclusion criteria based on methodological quality standards.""",
        "ai_system_prompt": DEFAULT_SYSTEM_PROMPT, 
        "ai_output_format_instructions": DEFAULT_OUTPUT_INSTRUCTIONS
    }
}

# --- Helper to create a blank criteria dict (empty fields) ---

def _make_blank_from_dict(source: Dict) -> Dict:
    blank = {}
    for k, v in source.items():
        if k.endswith(('_include', '_exclude', '_maybe')) or k in ('other_inclusion', 'other_exclusion'):
            blank[k] = ""
        else:
            blank[k] = v
    return blank

def get_blank_criteria_for_framework(framework_id: str) -> Dict:
    default_key = SUPPORTED_CRITERIA_FRAMEWORKS.get(framework_id, {}).get('default_criteria_key')
    if default_key and default_key in DEFAULT_FRAMEWORK_VALUES:
        return _make_blank_from_dict(DEFAULT_FRAMEWORK_VALUES[default_key])
    # fallback to PICOT structure
    picot_default = DEFAULT_FRAMEWORK_VALUES.get('PICOT_DEFAULT', {})
    return _make_blank_from_dict(picot_default)

# USER_CRITERIA structure and initialization
USER_CRITERIA: Dict[str, any] = {
    "framework": "PICOT",  # Default framework
    "criteria": get_blank_criteria_for_framework("PICOT")
}

# --- Getter and Setter Functions for Multi-Framework Support ---
def get_llm_providers_info():
    return SUPPORTED_LLM_PROVIDERS

def get_supported_criteria_frameworks() -> Dict:
    return SUPPORTED_CRITERIA_FRAMEWORKS

def get_default_criteria_for_framework(framework_id: str) -> Dict:
    framework_config = SUPPORTED_CRITERIA_FRAMEWORKS.get(framework_id)
    if framework_config:
        default_key = framework_config.get("default_criteria_key")
        if default_key and default_key in DEFAULT_FRAMEWORK_VALUES:
            # Return a copy to prevent modification of global defaults
            return DEFAULT_FRAMEWORK_VALUES[default_key].copy() 
    # Fallback to PICOT's defaults if specified framework or its defaults are not found
    # Ensure PICOT_DEFAULT always exists in DEFAULT_FRAMEWORK_VALUES with some content
    return DEFAULT_FRAMEWORK_VALUES.get("PICOT_DEFAULT", {}).copy()

def get_current_framework_id() -> str:
    global USER_CRITERIA
    if USER_CRITERIA and "framework" in USER_CRITERIA and USER_CRITERIA["framework"] in SUPPORTED_CRITERIA_FRAMEWORKS:
        return USER_CRITERIA["framework"]
    return "PICOT" # Default framework if not set or invalid

def get_current_criteria_object() -> Dict: # This returns the criteria data for the current framework
    global USER_CRITERIA
    current_framework = get_current_framework_id()
    if not USER_CRITERIA or USER_CRITERIA.get("framework") != current_framework or "criteria" not in USER_CRITERIA:
        # If USER_CRITERIA is not set, not for the current framework, or missing criteria, initialize/reset
        USER_CRITERIA = {
            "framework": current_framework,
            "criteria": get_blank_criteria_for_framework(current_framework)
        }
    return USER_CRITERIA["criteria"]

def set_user_criteria(framework_id: str, criteria_data_dict: Dict):
    global USER_CRITERIA
    USER_CRITERIA = {
        "framework": framework_id,
        "criteria": criteria_data_dict
    }

def reset_to_default_criteria():
    global USER_CRITERIA
    current_framework = get_current_framework_id()
    USER_CRITERIA = {
        "framework": current_framework,
        "criteria": get_blank_criteria_for_framework(current_framework)
    }

def get_screening_criteria() -> str:
    current_framework_id = get_current_framework_id()
    current_criteria_data = get_current_criteria_object()
    
    framework_config = SUPPORTED_CRITERIA_FRAMEWORKS.get(current_framework_id)
    
    if not framework_config or "template_string" not in framework_config:
        # Fallback to a very basic or error string if template is missing
        return f"ERROR: Template string not found for framework '{current_framework_id}'."

    template_str = framework_config["template_string"]
    
    # Prepare format_kwargs with all expected keys from the template string
    format_kwargs = {"framework_display_name": framework_config.get("display_name", current_framework_id)}
    
    for element in framework_config.get("elements", []):
        el_id = element["id"]
        if el_id == "other":
            format_kwargs["other_inclusion"] = current_criteria_data.get("other_inclusion", "(not specified)")
            format_kwargs["other_exclusion"] = current_criteria_data.get("other_exclusion", "(not specified)")
        else:
            for aspect in ["include", "exclude", "maybe"]:
                key_in_template = f"{el_id}_{aspect}" # e.g., p_include, s_maybe
                format_kwargs[key_in_template] = current_criteria_data.get(key_in_template, "(not specified)")
                
    try:
        return template_str.format(**format_kwargs).strip()
    except KeyError as e:
        return f"ERROR: Missing key '{str(e)}' for formatting template of framework '{current_framework_id}'."

# --- LLM Config Getters (Mostly unchanged) ---
def get_current_llm_config(session_data):
    default_provider_name = list(SUPPORTED_LLM_PROVIDERS.keys())[0]
    provider_name = session_data.get("selected_llm_provider", default_provider_name)
    if provider_name not in SUPPORTED_LLM_PROVIDERS:
        provider_name = default_provider_name
    provider_config = SUPPORTED_LLM_PROVIDERS[provider_name]
    default_model_id = provider_config["models"][0]["id"] if provider_config["models"] else None
    model_id = session_data.get("selected_llm_model_id", default_model_id)
    if not model_id or model_id not in [m['id'] for m in provider_config['models']]:
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
