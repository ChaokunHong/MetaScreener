"""
Document Quality Assessment AI Prompt Templates

This module contains quality assessment prompt templates designed for various document types,
optimized to guide AI in evaluating document quality. Each template is tailored to the 
assessment criteria for a specific document type with enhanced rigor and logical reasoning.
"""

from typing import Dict, List, Optional

# Ultra-rigorous general system prompt designed to minimize hallucinations
GENERAL_SYSTEM_PROMPT = """
You are a professional medical literature quality assessment expert with extensive training in standardized quality assessment tools.

CRITICAL ASSESSMENT CONSTRAINTS:
1. BASE EVERY JUDGMENT STRICTLY ON TEXTUAL EVIDENCE - Never infer, assume, or speculate beyond what is explicitly stated
2. DISTINGUISH CLEARLY between "explicitly stated," "implied but not stated," and "not mentioned"
3. WHEN EVIDENCE IS INSUFFICIENT - Always choose the more conservative/cautious judgment
4. QUOTE EXACT TEXT - Every claim must be supported by direct quotations from the document
5. ACKNOWLEDGE LIMITATIONS - Explicitly state when information is missing or unclear

PROHIBITED BEHAVIORS:
- Making assumptions about unstated methodological details
- Inferring quality based on journal reputation or author credentials
- Filling gaps with "reasonable assumptions"
- Using general knowledge to supplement missing information
- Providing judgments without explicit textual support

MANDATORY REASONING STRUCTURE:
1. EVIDENCE REQUIREMENT ANALYSIS: What specific evidence does this criterion require?
2. SYSTEMATIC TEXT SEARCH: What relevant information exists in the document?
3. EVIDENCE SUFFICIENCY EVALUATION: Is the found evidence adequate for a definitive judgment?
4. CONSERVATIVE JUDGMENT APPLICATION: What is the most defensible conclusion based solely on available evidence?

OUTPUT REQUIREMENTS:
- Use only the specified judgment categories (no intermediate terms)
- Provide exact quotations as evidence
- Acknowledge any information gaps or uncertainties
- Maintain consistent terminology throughout assessment
"""

# Simplified RCT assessment prompt with reliable JSON format
RCT_ASSESSMENT_PROMPT = """
TASK: Evaluate this RCT using Cochrane Risk of Bias 2.0 (RoB 2) standards with maximum precision and minimal interpretation.

ASSESSMENT CRITERION: {criterion_text}
CRITERION GUIDANCE: {criterion_guidance}

DOCUMENT CONTENT:
{document_text}

MANDATORY ASSESSMENT PROTOCOL:

PHASE 1: EVIDENCE REQUIREMENT SPECIFICATION
Determine exactly what textual evidence this RoB 2 criterion requires:
- What specific methodological information must be present?
- What exact procedures or processes need description?
- What level of detail is minimally acceptable?

PHASE 2: SYSTEMATIC EVIDENCE EXTRACTION
Search the document systematically for:
a) Direct statements about the criterion
b) Methodological descriptions relevant to the criterion
c) Any procedural details that address the criterion
d) Absence of expected information

PHASE 3: EVIDENCE ADEQUACY ASSESSMENT
For each piece of found evidence, determine:
- Is this statement explicit and unambiguous?
- Does this fully address the criterion requirement?
- Are there gaps in the information provided?
- What aspects remain unclear or unstated?

PHASE 4: CONSERVATIVE RISK CLASSIFICATION
Apply this decision logic:

LOW RISK: Award ONLY if:
- Explicit, detailed textual evidence fully demonstrates adherence to best practices
- No significant information gaps exist
- The described methods clearly minimize bias risk
- Evidence is unambiguous and complete

HIGH RISK: Award if:
- Explicit evidence demonstrates methodological flaws
- Clear bias sources are described or evident
- Inadequate procedures are explicitly reported

SOME CONCERNS: Award when:
- Information is partially reported but incomplete
- Methods are described but lack sufficient detail
- Some relevant information is missing
- Evidence suggests possible but not definite bias risk

CRITICAL CONSTRAINTS:
- Never assume unstated procedures were performed adequately
- Never infer quality from partial information
- Never supplement missing details with "standard practice" assumptions
- Always cite exact text passages as evidence
- Explicitly acknowledge when evidence is insufficient

Return assessment in this SIMPLE JSON format:
{{
  "judgment": "low risk/high risk/some concerns",
  "justification": "Detailed explanation based solely on documented evidence, citing exact text",
  "supporting_quotes": ["Exact quote 1 with context", "Exact quote 2 with context", "Exact quote 3 with context"],
  "evidence_quality": "high/medium/low",
  "limitations": "Any uncertainties or information gaps that affect confidence"
}}
"""

# Simplified Systematic Review assessment prompt
SYSTEMATIC_REVIEW_ASSESSMENT_PROMPT = """
TASK: Evaluate this systematic review using AMSTAR-2 standards with maximum objectivity and evidence-based reasoning.

ASSESSMENT CRITERION: {criterion_text}
CRITERION GUIDANCE: {criterion_guidance}

DOCUMENT CONTENT:
{document_text}

STRICT EVALUATION PROTOCOL:

PHASE 1: AMSTAR-2 REQUIREMENT SPECIFICATION
Define precisely what this AMSTAR-2 item requires:
- What specific methodological elements must be reported?
- What level of detail constitutes adequate reporting?
- Is this a critical or non-critical AMSTAR-2 item?
- What are the minimum standards for "Yes" vs "Partial Yes" vs "No"?

PHASE 2: COMPREHENSIVE EVIDENCE MAPPING
Systematically search document sections for:
- Methods section: [Scan for relevant methodological descriptions]
- Results section: [Look for implementation evidence]
- Appendices/supplements: [Check for additional methodological details]
- Tables/figures: [Examine for procedural information]

PHASE 3: EVIDENCE COMPLETENESS EVALUATION
For each piece of information found:
- Does this provide complete information for the AMSTAR-2 requirement?
- Are the described procedures adequate and appropriate?
- What specific details are missing or unclear?
- How does this compare to AMSTAR-2 best practice standards?

PHASE 4: STANDARDIZED JUDGMENT APPLICATION
Apply these precise criteria:

YES: Award ONLY when:
- Complete, explicit description of all required elements
- Methods clearly meet or exceed AMSTAR-2 standards
- No significant information gaps
- Implementation is adequately documented

PARTIAL YES: Award when:
- Core elements are described but lack some detail
- Methods are generally appropriate but incompletely reported
- Some required information is missing but key components present
- Implementation is partially documented

NO: Award when:
- Required elements are not described
- Methods clearly inadequate or inappropriate
- Substantial information gaps prevent assessment
- No evidence of implementation

OBJECTIVITY SAFEGUARDS:
- Base judgments solely on what is explicitly reported
- Do not credit unstated but "implied" procedures
- Acknowledge when information is genuinely unclear
- Distinguish between "not reported" and "inadequately reported"
- Avoid assumptions about "standard practices"

Return assessment in this SIMPLE JSON format:
{{
  "judgment": "yes/partial yes/no",
  "evidence_basis": "Detailed justification citing specific text passages",
  "supporting_quotes": ["Exact methodological quote 1", "Exact methodological quote 2", "Exact methodological quote 3"],
  "quality_implications": "Assessment of how this item affects overall review quality",
  "reporting_gaps": "Specific information that should have been reported but was missing"
}}
"""

# Simplified Cohort Study assessment with ultra-precision
COHORT_STUDY_ASSESSMENT_PROMPT = """
TASK: Evaluate this cohort study using Newcastle-Ottawa Scale (NOS) with maximum precision and evidence-based scoring.

ASSESSMENT CRITERION: {criterion_text}
CRITERION GUIDANCE: {criterion_guidance}

DOCUMENT CONTENT:
{document_text}

ULTRA-PRECISE NOS EVALUATION PROTOCOL:

PHASE 1: NOS ITEM SPECIFICATION
Define exact requirements for this NOS item:
- Which NOS domain does this belong to (Selection/Comparability/Outcome)?
- What specific study characteristics must be documented?
- What constitutes "adequate" vs "inadequate" for star award?
- What is the maximum number of stars available for this item?

PHASE 2: METHODICAL EVIDENCE COLLECTION
Search systematically for evidence of:
- Study design and population characteristics
- Participant selection and recruitment procedures
- Exposure definition and measurement methods
- Outcome definition and ascertainment procedures
- Follow-up procedures and completeness
- Comparability and matching procedures

PHASE 3: STAR CRITERIA VERIFICATION
Apply strict NOS criteria:
- Is there explicit documentation of required procedures?
- Do the described methods meet NOS standards for quality?
- Are procedures adequate to minimize bias for this domain?
- Is the evidence clear and unambiguous?

PHASE 4: CONSERVATIVE STAR ASSIGNMENT
Award stars using this logic:

STAR AWARDED: Only when:
- Explicit, detailed documentation of high-quality procedures
- Methods clearly meet or exceed NOS standards
- No significant methodological concerns
- Evidence is unambiguous and complete

NO STAR AWARDED: When:
- Required information is missing or inadequate
- Methods do not meet NOS quality standards
- Significant methodological limitations present
- Evidence is unclear or insufficient

EVIDENCE HIERARCHY FOR SCORING:
1. Explicit methodological statements (strongest evidence)
2. Detailed procedural descriptions (strong evidence)
3. Results that imply procedures (moderate evidence)
4. Vague or incomplete descriptions (weak evidence)

Return assessment in this SIMPLE JSON format:
{{
  "judgment": "star awarded/no star awarded",
  "scoring_rationale": "Detailed explanation with exact quotes",
  "supporting_quotes": ["Exact quote supporting decision 1", "Exact quote supporting decision 2"],
  "evidence_strength": "explicit/detailed/moderate/weak/insufficient",
  "confidence_level": "high/medium/low"
}}
"""

# Simplified Case-Control assessment
CASE_CONTROL_ASSESSMENT_PROMPT = """
TASK: Evaluate this case-control study using Newcastle-Ottawa Scale (NOS) case-control version with maximum objectivity.

ASSESSMENT CRITERION: {criterion_text}
CRITERION_GUIDANCE: {criterion_guidance}

DOCUMENT CONTENT:
{document_text}

RIGOROUS CASE-CONTROL NOS PROTOCOL:

PHASE 1: CASE-CONTROL DESIGN VERIFICATION
Confirm study characteristics:
- Is this definitively a case-control design?
- How are cases defined and identified?
- How are controls selected and matched?
- What is the exposure measurement approach?

PHASE 2: NOS ITEM REQUIREMENT ANALYSIS
For this specific NOS item:
- What case-control specific requirements must be met?
- How do standards differ from cohort study NOS items?
- What constitutes adequate vs inadequate methodology?
- What are the specific bias risks this item addresses?

PHASE 3: SYSTEMATIC EVIDENCE EXTRACTION
Document evidence for:
- Case definition and validation procedures
- Control selection and matching strategies
- Exposure ascertainment methods and quality
- Response rates and non-response handling
- Comparability between cases and controls

PHASE 4: CONSERVATIVE NOS SCORING
Apply case-control specific criteria with maximum objectivity.

Return assessment in this SIMPLE JSON format:
{{
  "judgment": "star awarded/no star awarded",
  "evidence_basis": "Detailed justification with quotes",
  "supporting_quotes": ["Quote 1", "Quote 2"],
  "methodological_quality": "high/medium/low/poor",
  "confidence_level": "high/medium/low"
}}
"""

# Prompt mapping dictionary
ASSESSMENT_PROMPTS_BY_TYPE = {
    "RCT": RCT_ASSESSMENT_PROMPT,
    "Systematic Review": SYSTEMATIC_REVIEW_ASSESSMENT_PROMPT,
    "Cohort Study": COHORT_STUDY_ASSESSMENT_PROMPT,
    "Case-Control Study": CASE_CONTROL_ASSESSMENT_PROMPT,
    # Add other types following the same ultra-rigorous pattern
}

def get_assessment_prompt(document_type: str, criterion_text: str, criterion_guidance: Optional[str], document_text: str) -> Dict:
    """
    Get ultra-rigorous assessment prompt optimized for reliability and minimal hallucination
    
    Parameters:
        document_type: Document type
        criterion_text: Evaluation criterion text
        criterion_guidance: Criterion guidance (optional)
        document_text: Document content
        
    Returns:
        Dictionary containing system prompt and user prompt optimized for LLM reliability
    """
    # Get the ultra-rigorous prompt template
    prompt_template = ASSESSMENT_PROMPTS_BY_TYPE.get(document_type, COHORT_STUDY_ASSESSMENT_PROMPT)
    
    # Enhanced guidance handling with explicit instruction
    if not criterion_guidance or criterion_guidance.strip() == "":
        effective_guidance = "No specific guidance provided. Apply general principles of the assessment tool with maximum conservatism. When in doubt, choose the more cautious judgment."
    else:
        effective_guidance = criterion_guidance
    
    # Format with truncated text to avoid context overflow
    formatted_prompt = prompt_template.format(
        criterion_text=criterion_text,
        criterion_guidance=effective_guidance,
        document_text=document_text[:25000]  # Reduced to ensure reliability
    )
    
    return {
        "system_prompt": GENERAL_SYSTEM_PROMPT,
        "main_prompt": formatted_prompt,
        # Suggested LLM parameters for optimal performance
        "recommended_parameters": {
            "temperature": 0.1,  # Very low for consistency
            "top_p": 0.8,       # Focused sampling
            "frequency_penalty": 0.2,  # Reduce repetition
            "presence_penalty": 0.1,   # Encourage completeness
            "max_tokens": 1500   # Adequate for detailed response
        }
    } 