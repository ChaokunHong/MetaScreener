# Quality Assessment Prompt Enhancement Summary

## Overview

This comprehensive enhancement focuses on the **two core prompts** that form the foundation of the quality assessment system: **Document Classification** and **Quality Evaluation**. These prompts have been redesigned with ultra-rigorous standards to maximize credibility, logical consistency, and LLM reliability while minimizing hallucinations.

## Core Prompt Philosophy: Maximum Rigor, Minimal Hallucination

### 🎯 Core Design Principles

**1. Evidence-Only Foundation**
- Every judgment must be based on explicit textual evidence
- Prohibition of inference, assumption, or speculation
- Mandatory direct quotations for all claims
- Clear distinction between "stated," "implied," and "not mentioned"

**2. Conservative Judgment Approach**
- When evidence is insufficient → choose more cautious assessment
- When evidence conflicts → acknowledge uncertainty
- When information missing → explicitly state limitations
- Prefer "some concerns" over forced definitive judgments

**3. Structured Decision Trees**
- Phase-by-phase evaluation protocols
- Explicit criteria for each judgment category
- Mandatory systematic evidence collection
- Required justification for final decisions

## 🔧 Ultra-Rigorous Document Classification Prompt

### Enhanced Design Features

**Phase-Based Classification Protocol:**
```
PHASE 1: EXPLICIT DESIGN FEATURE EXTRACTION
PHASE 2: METHODOLOGICAL MARKER VERIFICATION  
PHASE 3: STATISTICAL APPROACH DOCUMENTATION
PHASE 4: CONVERGENT EVIDENCE EVALUATION
PHASE 5: CONSERVATIVE CLASSIFICATION ASSIGNMENT
```

**Strict Classification Standards:**
```
RCT: Award ONLY if:
- Explicit randomization procedures are described
- Control/comparison groups are clearly defined
- Intervention allocation is explicitly described
- Multiple convergent evidence types support RCT classification
```

**Prohibited Behaviors:**
```
- Inferring study type from journal names, author affiliations, or publication context
- Assuming standard procedures that are not explicitly described
- Classifying based on single pieces of ambiguous evidence
- Using general knowledge to supplement missing methodological information
- Making assumptions about study design based on statistical methods alone
```

## 🔧 Ultra-Rigorous Quality Assessment Prompt

### Enhanced Design Features

**Critical Assessment Constraints:**
```
1. BASE EVERY JUDGMENT STRICTLY ON TEXTUAL EVIDENCE - Never infer, assume, or speculate beyond what is explicitly stated
2. DISTINGUISH CLEARLY between "explicitly stated," "implied but not stated," and "not mentioned"
3. WHEN EVIDENCE IS INSUFFICIENT - Always choose the more conservative/cautious judgment
4. QUOTE EXACT TEXT - Every claim must be supported by direct quotations from the document
5. ACKNOWLEDGE LIMITATIONS - Explicitly state when information is missing or unclear
```

**Mandatory Assessment Protocol:**
```
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
```

## 🎯 Hallucination Prevention Mechanisms

### 1. Explicit Prohibition Lists
Both prompts contain detailed lists of prohibited behaviors:
- No assumptions about unstated procedures
- No inference from partial information
- No supplementation with general knowledge
- No forced classifications when evidence insufficient

### 2. Evidence Hierarchy Requirements
Clear prioritization of evidence types:
- **Strongest**: Explicit methodological statements
- **Strong**: Detailed procedural descriptions  
- **Moderate**: Statistical method specifications
- **Weak**: Terminology usage
- **Insufficient**: Implied or assumed features (prohibited)

### 3. Structured Decision Logic
Mandatory systematic evaluation phases prevent shortcuts:
- Evidence requirement analysis
- Systematic text search
- Evidence sufficiency evaluation
- Conservative judgment application

### 4. Uncertainty Acknowledgment
Explicit requirements to acknowledge limitations:
- Missing information gaps
- Conflicting evidence
- Unclear statements
- Confidence level assessments

## 🎛️ LLM Parameter Optimization

### Recommended Parameters for Maximum Reliability

**Ultra-Conservative Settings:**
```json
{
  "temperature": 0.1,     // Very low for consistency
  "top_p": 0.8,          // Focused sampling
  "frequency_penalty": 0.2, // Reduce repetition
  "presence_penalty": 0.1,  // Encourage completeness
  "max_tokens": 1500       // Adequate for detailed response
}
```

**Parameter Justification:**
- **Temperature 0.1**: Minimizes creative interpretation, maximizes consistency
- **Top_p 0.8**: Focuses on high-probability tokens while allowing necessary detail
- **Frequency penalty 0.2**: Reduces repetitive phrasing without losing emphasis
- **Presence penalty 0.1**: Encourages comprehensive coverage of all required elements

## 🔍 Enhanced JSON Response Structures

### Document Classification Response
```json
{
  "design_feature_analysis": {
    "explicit_design_statements": ["[Direct quote 1]", "[Direct quote 2]"],
    "temporal_descriptions": ["[Quote about timing]", "[Quote about follow-up]"],
    "participant_descriptions": ["[Quote about subjects]", "[Quote about population]"],
    "comparison_group_descriptions": ["[Quote about controls]", "[Quote about comparisons]"]
  },
  "convergent_evidence_assessment": {
    "design_method_alignment": "[Do design statements match methodological descriptions?]",
    "evidence_consistency": "[Are all evidence types pointing to same classification?]",
    "conflicting_signals": ["[Any contradictory evidence]", "[Areas of uncertainty]"]
  }
}
```

### Quality Assessment Response
```json
{
  "evidence_analysis": {
    "required_evidence_type": "[Specify exactly what evidence this criterion requires]",
    "evidence_present": "[List all relevant information found in document with exact quotes]",
    "evidence_absent": "[Specify what required information is missing]",
    "evidence_quality": "[Assess completeness and clarity of available evidence]"
  },
  "decision_logic": {
    "low_risk_criteria_met": "yes/no [with specific justification]",
    "conservative_reasoning": "[Explain why this judgment is most defensible]"
  }
}
```

## 📊 Quality Assurance Mechanisms

### 1. Multi-Layer Verification
- Evidence requirement specification
- Systematic evidence extraction
- Evidence adequacy assessment
- Conservative judgment application

### 2. Transparency Requirements
- Exact quotations mandatory
- Reasoning steps documented
- Limitations explicitly acknowledged
- Confidence levels assessed

### 3. Consistency Enforcement
- Standardized terminology usage
- Uniform judgment categories
- Systematic evaluation protocols
- Objective assessment criteria

## 🚀 Expected Impact on Assessment Quality

### Credibility Enhancement
- **Evidence-Based Judgments**: Every conclusion supported by direct textual evidence
- **Conservative Approach**: Reduces false positives and overconfident assessments
- **Transparency**: Complete reasoning trail enables verification and trust

### Logical Consistency
- **Systematic Protocols**: Phase-based evaluation ensures comprehensive coverage
- **Decision Trees**: Clear logic paths prevent arbitrary judgments
- **Convergent Evidence**: Multiple evidence types must align for confident classification

### Reliability Optimization
- **Hallucination Minimization**: Strict constraints prevent AI speculation
- **Parameter Tuning**: Low-temperature settings maximize consistency
- **Uncertainty Handling**: Explicit acknowledgment of limitations and gaps

## 💡 Implementation Recommendations

### 1. Gradual Deployment
- Pilot testing with known documents
- Comparison with expert assessments
- Iterative refinement based on performance

### 2. Quality Monitoring
- Regular assessment of AI response quality
- Tracking of uncertainty acknowledgments
- Monitoring for consistency across similar documents

### 3. Expert Validation
- Periodic review by domain experts
- Validation of assessment criteria application
- Refinement of judgment standards as needed

## 🔒 Technical Safeguards

### Code-Level Protections
- Input validation and sanitization
- Response parsing with fallback mechanisms
- Error handling with conservative defaults
- Logging of assessment reasoning for audit

### Performance Optimization
- Context window management (25,000 character limit)
- Efficient prompt structuring
- Strategic information prioritization
- Response time optimization

This ultra-rigorous approach ensures that the two core prompts deliver maximum reliability and credibility for quality assessment while maintaining the sophisticated logical reasoning necessary for accurate evaluations. 