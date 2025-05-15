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
Based on the provided document content, please assess the specific evaluation criteria. Your assessment should:
1. Be objective: Based on textual facts rather than subjective judgments
2. Be rigorous: Conducted strictly according to the standards of the assessment tool
3. Be specific: Cite specific text from the document as the basis for evaluation
4. Be clear: Clearly indicate parts that meet or fail to meet standards

Please provide your assessment results in the specified JSON format.
"""

# RCT assessment prompt - Cochrane RoB 2 tool
RCT_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following randomized controlled trial (RCT) based on the Cochrane Risk of Bias 2 (RoB 2) tool.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

Please make an assessment judgment based on the following RCT document content:

{document_text}

After analyzing the text, determine the risk level (low risk/high risk/some concerns) and provide reasoning and evidence for your judgment.

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

Please make an assessment judgment based on the following systematic review/meta-analysis document content:

{document_text}

After analyzing the text, determine whether the criterion requirements are met (yes/no/partial yes) and provide reasoning and evidence for your judgment.

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

Please make an assessment judgment based on the following cohort study document content:

{document_text}

After analyzing the text, determine whether a star (★) should be awarded and provide reasoning and evidence for your judgment.

Return results in the following JSON format:
```json
{{
  "judgment": "star awarded/no star awarded [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Case-Control Study assessment prompt - Newcastle-Ottawa Scale
CASE_CONTROL_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following case-control study based on the Newcastle-Ottawa Scale (NOS).

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

Please make an assessment judgment based on the following case-control study document content:

{document_text}

After analyzing the text, determine whether a star (★) should be awarded and provide reasoning and evidence for your judgment.

Return results in the following JSON format:
```json
{{
  "judgment": "star awarded/no star awarded [select one]",
  "reason": "[detailed explanation of why you gave this assessment, citing key text to support it]",
  "evidence_quotes": ["[direct quote from the text as evidence 1]", "[direct quote from the text as evidence 2]"]
}}
```
"""

# Cross-sectional Study assessment prompt - AXIS tool
CROSS_SECTIONAL_ASSESSMENT_PROMPT = """
Please evaluate the quality of the following cross-sectional study based on the AXIS tool.

Evaluation criterion: {criterion_text}

Criterion guidance: {criterion_guidance}

Please make an assessment judgment based on the following cross-sectional study document content:

{document_text}

After analyzing the text, determine whether the criterion requirements are met (yes/no/unclear) and provide reasoning and evidence for your judgment.

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

Please make an assessment judgment based on the following diagnostic accuracy study document content:

{document_text}

After analyzing the text, determine the risk of bias or applicability concerns (low/high/unclear) and provide reasoning and evidence for your judgment.

Return results in the following JSON format:
```json
{{
  "judgment": "low risk/high risk/unclear [select one]",
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

Please make an assessment judgment based on the following qualitative research document content:

{document_text}

After analyzing the text, determine whether the criterion requirements are met (yes/no/unclear) and provide reasoning and evidence for your judgment.

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

Please make an assessment judgment based on the following economic evaluation research document content:

{document_text}

After analyzing the text, determine whether the reporting requirements are met (fully reported/partially reported/not reported) and provide reasoning and evidence for your judgment.

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

Please make an assessment judgment based on the following animal research document content:

{document_text}

After analyzing the text, determine whether the reporting requirements are met (yes/no/partial yes) and provide reasoning and evidence for your judgment.

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