"""
Document Quality Assessment AI Prompt Templates

This module contains quality assessment prompt templates designed for various document types,
optimized to guide AI in evaluating document quality. Each template is tailored to the 
assessment criteria for a specific document type.
"""

from typing import Dict, List, Optional

# General system prompt template, applicable to all document types
GENERAL_SYSTEM_PROMPT = """
You are a professional medical literature quality assessment expert, skilled in using standardized tools to conduct rigorous quality assessments of various types of medical research literature.

Based on the provided document content, please assess the specific evaluation criterion. Your assessment should:
1. Be objective: Based solely on textual facts rather than subjective judgments
2. Be rigorous: Conducted strictly according to the standards of the assessment tool
3. Be specific: Cite specific text from the document as the basis for evaluation
4. Be clear: Clearly indicate parts that meet or fail to meet standards
5. Be comprehensive: Consider all relevant information in the document

For complex or conditional criteria (those that depend on answers to previous criteria), carefully determine whether the criterion is applicable. For example, if a criterion starts with "If...", determine if the condition is met before proceeding with the assessment.

Please follow the specific judgment categories allowed for each assessment tool (e.g., "yes/no/partial yes" for AMSTAR-2, "low risk/high risk/some concerns" for RoB 2). Do not create your own judgment categories.

Provide detailed reasoning and multiple evidence quotes whenever possible to support your judgment.

Please provide your assessment results in the specified JSON format.
"""

# RCT assessment prompt - Cochrane RoB 2 tool
RCT_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following randomized controlled trial (RCT) based on the Cochrane Risk of Bias 2 (RoB 2) tool.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

Some criteria in RoB 2 are conditional - they only apply if previous criteria are answered in a certain way. If the criterion begins with "If" followed by letters like Y/PY/NI (Yes/Probably Yes/No Information), determine if the condition is applicable based on what you can infer from the text.

Please make an assessment judgment based on the following RCT document content:

{document_text}

After analyzing the text, determine the risk level:
- "low risk" - The study is judged to be at low risk of bias for this domain
- "high risk" - The study is judged to be at high risk of bias for this domain
- "some concerns" - The study is judged to have some concerns for this domain

Return results in the following JSON format:
```json
{{
  "judgment": "low risk/high risk/some concerns [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Systematic Review assessment prompt - AMSTAR-2 tool
SYSTEMATIC_REVIEW_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following systematic review/meta-analysis based on the AMSTAR-2 tool.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

Some criteria in AMSTAR-2 specifically apply to meta-analyses. For these criteria (often containing phrases like "If meta-analysis was performed..."), first determine if a meta-analysis was actually conducted in the review. If no meta-analysis was performed and the criterion is only relevant for meta-analyses, indicate this in your assessment.

Please make an assessment judgment based on the following systematic review/meta-analysis document content:

{document_text}

After analyzing the text, determine whether the criterion requirements are met:
- "yes" - The criterion is fully satisfied
- "partial yes" - The criterion is partially satisfied (typically when only some of the requirements are met)
- "no" - The criterion is not satisfied

Return results in the following JSON format:
```json
{{
  "judgment": "yes/partial yes/no [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Cohort Study assessment prompt - Newcastle-Ottawa Scale
COHORT_STUDY_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following cohort study based on the Newcastle-Ottawa Scale (NOS).

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

The Newcastle-Ottawa Scale uses a star system (★) for quality assessment. Some criteria (particularly in the "Comparability" section) can receive up to 2 stars, while most receive 0 or 1 star.

Please make an assessment judgment based on the following cohort study document content:

{document_text}

After analyzing the text, determine whether a star (★) should be awarded and provide reasoning and evidence for your judgment.

Return results in the following JSON format:
```json
{{
  "judgment": "star awarded/no star awarded [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it, including specific mentions of which star-awarding criteria were met]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Case-Control Study assessment prompt - Newcastle-Ottawa Scale
CASE_CONTROL_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following case-control study based on the Newcastle-Ottawa Scale (NOS).

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

The Newcastle-Ottawa Scale uses a star system (★) for quality assessment. Some criteria (particularly in the "Comparability" section) can receive up to 2 stars, while most receive 0 or 1 star.

Please make an assessment judgment based on the following case-control study document content:

{document_text}

After analyzing the text, determine whether a star (★) should be awarded and provide reasoning and evidence for your judgment.

Return results in the following JSON format:
```json
{{
  "judgment": "star awarded/no star awarded [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it, including specific mentions of which star-awarding criteria were met]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Cross-sectional Study assessment prompt - AXIS tool
CROSS_SECTIONAL_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following cross-sectional study based on the AXIS tool.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

The AXIS tool assesses the quality of cross-sectional studies across methodology, reporting quality, and study design elements.

Please make an assessment judgment based on the following cross-sectional study document content:

{document_text}

After analyzing the text, determine whether the criterion requirements are met:
- "yes" - The criterion is satisfied
- "no" - The criterion is not satisfied
- "unclear" - There is insufficient information to determine if the criterion is met

Return results in the following JSON format:
```json
{{
  "judgment": "yes/no/unclear [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Diagnostic Accuracy Study assessment prompt - QUADAS-2 tool
DIAGNOSTIC_STUDY_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following diagnostic accuracy study based on the QUADAS-2 tool.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

QUADAS-2 evaluates diagnostic accuracy studies across four key domains: patient selection, index test, reference standard, and flow and timing. Each domain is assessed for risk of bias, and the first three domains are also assessed for concerns about applicability. Note that some criteria evaluate risk of bias while others evaluate applicability concerns.

Please make an assessment judgment based on the following diagnostic accuracy study document content:

{document_text}

After analyzing the text, determine the appropriate judgment:
- For risk of bias questions: "low risk" / "high risk" / "unclear"
- For applicability questions: "low concern" / "high concern" / "unclear"

Return results in the following JSON format:
```json
{{
  "judgment": "low risk/high risk/unclear [for risk of bias] OR low concern/high concern/unclear [for applicability]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Qualitative Research assessment prompt - CASP Qualitative Research tool
QUALITATIVE_RESEARCH_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following qualitative research based on the CASP Qualitative Research tool.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

The CASP Qualitative Research tool assesses methodological rigor and trustworthiness of qualitative research. Pay special attention to how data collection, analysis, and interpretation were conducted.

Please make an assessment judgment based on the following qualitative research document content:

{document_text}

After analyzing the text, determine whether the criterion requirements are met:
- "yes" - The criterion is clearly met
- "no" - The criterion is clearly not met
- "unclear" - There is insufficient information to determine if the criterion is met

Return results in the following JSON format:
```json
{{
  "judgment": "yes/no/unclear [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Economic Evaluation assessment prompt - CHEERS statement
ECONOMIC_EVALUATION_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following economic evaluation research based on the CHEERS 2022 statement.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

The CHEERS 2022 statement evaluates the reporting quality of health economic evaluations. When assessing, consider that economic evaluations vary in their methods (cost-effectiveness, cost-utility, cost-benefit, etc.) and some elements may be reported differently based on the specific type of analysis.

Please pay particular attention to:
- Appropriate economic methods for the research question
- Clear reporting of costs and outcomes
- Proper sensitivity analyses to address uncertainty
- Transparent reporting of model assumptions (if a model-based analysis)

Please make an assessment judgment based on the following economic evaluation research document content:

{document_text}

After analyzing the text, determine whether the reporting requirements are met:
- "fully reported" - The information is completely reported as required
- "partially reported" - Some of the required information is reported, but with significant gaps
- "not reported" - The required information is missing or substantially inadequate

Return results in the following JSON format:
```json
{{
  "judgment": "fully reported/partially reported/not reported [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Animal Research assessment prompt - ARRIVE 2.0 guidelines
ANIMAL_RESEARCH_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following animal research based on the ARRIVE 2.0 guidelines.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

The ARRIVE 2.0 guidelines focus on improving the reporting of animal research to maximize transparency and reproducibility. When assessing, pay particular attention to:
- Detailed reporting of study design elements
- Complete description of animals used (species, strain, sex, age, etc.)
- Appropriate statistical methods and sample size calculations
- Proper reporting of ethical considerations and animal welfare
- Description of experimental procedures with sufficient detail for replication

Please make an assessment judgment based on the following animal research document content:

{document_text}

After analyzing the text, determine whether the reporting requirements are met:
- "yes" - The criterion is fully met with comprehensive reporting
- "partial yes" - The criterion is partially met with some information reported but gaps remain
- "no" - The criterion is not met or critically inadequate information is provided

Return results in the following JSON format:
```json
{{
  "judgment": "yes/partial yes/no [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Prompt mapping dictionary, to get the corresponding prompt based on document type
ASSESSMENT_PROMPTS_BY_TYPE = {
    "RCT": RCT_ASSESSMENT_PROMPT,
    "Systematic Review": SYSTEMATIC_REVIEW_ASSESSMENT_PROMPT,
    "Cohort Study": COHORT_STUDY_ASSESSMENT_PROMPT,
    "Case-Control Study": CASE_CONTROL_ASSESSMENT_PROMPT,
    "Cross-sectional Study": CROSS_SECTIONAL_ASSESSMENT_PROMPT,
    "Diagnostic Study": DIAGNOSTIC_STUDY_ASSESSMENT_PROMPT,
    "Qualitative Research": QUALITATIVE_RESEARCH_ASSESSMENT_PROMPT,
    "Economic Evaluation": ECONOMIC_EVALUATION_ASSESSMENT_PROMPT,
    "Animal Research": ANIMAL_RESEARCH_ASSESSMENT_PROMPT
}

def get_assessment_prompt(document_type: str, criterion_text: str, criterion_guidance: Optional[str], document_text: str) -> Dict:
    """
    Get the corresponding assessment prompt based on document type and fill in parameters
    
    Parameters:
        document_type: Document type
        criterion_text: Evaluation criterion text
        criterion_guidance: Criterion guidance (optional)
        document_text: Document content
        
    Returns:
        Dictionary containing system prompt and user prompt
    """
    # Get the prompt template corresponding to the document type, use a default template if not found
    prompt_template = ASSESSMENT_PROMPTS_BY_TYPE.get(document_type, COHORT_STUDY_ASSESSMENT_PROMPT)
    
    # Fill in the template
    formatted_prompt = prompt_template.format(
        criterion_text=criterion_text,
        criterion_guidance=criterion_guidance if criterion_guidance else "No detailed guidance",
        document_text=document_text[:30000]  # Limit text length to avoid exceeding model context window
    )
    
    return {
        "system_prompt": GENERAL_SYSTEM_PROMPT,
        "main_prompt": formatted_prompt
    } 