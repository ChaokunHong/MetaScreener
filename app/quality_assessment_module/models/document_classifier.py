"""
Document Type Automatic Classification Model

This module provides automatic recognition functionality for literature types by analyzing the structure, content, and keywords of the document.
"""

import re
from typing import Dict, List, Tuple, Optional, Set

# Characteristic keywords and phrases for various document types
DOCUMENT_TYPE_KEYWORDS = {
    "RCT": {
        "strong": [
            r"\brandom(ly|ized|isation)\b", 
            r"\bRCT\b", 
            r"\bdouble(-|\s)blind\b",
            r"\bplacebo(-|\s)controlled\b",
            r"\ballocat(ed|ion)\s(to|into)\s(groups?|arms?)\b"
        ],
        "medium": [
            r"\bblind(ed|ing)\b", 
            r"\bcontrol\sgroup\b", 
            r"\btreatment\sarm\b", 
            r"\bintervention\sgroup\b",
            r"\btrial\sregistr(y|ation)\b"
        ]
    },
    "Systematic Review": {
        "strong": [
            r"\bsystematic(\s|\w)+review\b", 
            r"\bmeta(-|\s)analysis\b",
            r"\bPRISMA\b", 
            r"\bsearch(\s|\w)+strateg(y|ies)\b",
            r"\bdatabase(s)?\s(search|retrieval)\b"
        ],
        "medium": [
            r"\bsearch(\w+|\s)(PubMed|Medline|Embase|Cochrane)\b",
            r"\binclu(sion|ded)(\s|\w+)criteria\b", 
            r"\bexclu(sion|ded)(\s|\w+)criteria\b",
            r"\bdata\sextraction\b", 
            r"\bquality\sassessment\b"
        ]
    },
    "Cohort Study": {
        "strong": [
            r"\bcohort\sstudy\b", 
            r"\bprospective\scohort\b",
            r"\bretrospective\scohort\b", 
            r"\bfollow(ed|\s)up\sfor\b",
            r"\blongitudinal\sstudy\b"
        ],
        "medium": [
            r"\bfollow(-|\s)up\b", 
            r"\bincidence\b", 
            r"\bperson(-|\s)years\b",
            r"\brisk\sratio\b", 
            r"\bhazard\sratio\b"
        ]
    },
    "Case-Control Study": {
        "strong": [
            r"\bcase(-|\s)control\b", 
            r"\bcases\sand\scontrols\b",
            r"\bodds\sratio\b", 
            r"\bmatched\b"
        ],
        "medium": [
            r"\bexposed\svs\s(unexposed|non-exposed)\b", 
            r"\brisk\sfactors?\b",
            r"\bcontrol\sgroup\b", 
            r"\bstudy\sgroup\b"
        ]
    },
    "Cross-sectional Study": {
        "strong": [
            r"\bcross(-|\s)sectional\sstudy\b", 
            r"\bprevalence\sstudy\b",
            r"\bprevalence\sof\b", 
            r"\bsurvey\b"
        ],
        "medium": [
            r"\bpoint\sin\stime\b", 
            r"\bquestion(naire|aire)\b", 
            r"\bsampling\b",
            r"\bresponse\srate\b"
        ]
    },
    "Diagnostic Study": {
        "strong": [
            r"\bdiagnostic\s(accuracy|performance|test|study)\b", 
            r"\bsensitivity\sand\sspecificity\b",
            r"\bROC\s(curve|analysis)\b", 
            r"\breference\sstandard\b",
            r"\b(PPV|NPV|positive\spredictive\svalue|negative\spredictive\svalue)\b"
        ],
        "medium": [
            r"\bindex\stest\b", 
            r"\bgold\sstandard\b", 
            r"\bfalse\s(positive|negative)\b",
            r"\btrue\s(positive|negative)\b", 
            r"\bAUC\b"
        ]
    },
    "Qualitative Research": {
        "strong": [
            r"\bqualitative\s(study|research|analysis)\b",
            r"\bthematic\sanalysis\b",
            r"\bfocus\sgroup\b",
            r"\bin-depth\sinterview\b",
            r"\bthemes\semerged\b"
        ],
        "medium": [
            r"\bcontent\sanalysis\b",
            r"\bphenomenological\b",
            r"\bethnograph(y|ic)\b",
            r"\bgrounded\stheory\b",
            r"\bsaturation\b"
        ]
    },
    "Economic Evaluation": {
        "strong": [
            r"\bcost(-|\s)effective(ness)?\b",
            r"\bcost(-|\s)benefit\sanalysis\b",
            r"\bcost(-|\s)utility\sanalysis\b",
            r"\bINCR\b|\bincremental\scost(-|\s)effectiveness\sratio\b",
            r"\bbudget\simpact\sanalysis\b"
        ],
        "medium": [
            r"\beconomic\sevaluation\b",
            r"\bQALY\b",
            r"\bhealth\sutilities\b",
            r"\bdirect\scosts?\b",
            r"\bindirect\scosts?\b"
        ]
    }
}

# Document structure pattern definitions
STRUCTURE_PATTERNS = {
    "RCT": [
        r"(CONSORT|CLINICAL\sTRIAL)",
        r"(?i)(randomization|randomisation|randomization procedures?|randomisation procedures?)",
        r"(?i)(study design|trial design).*?(randomized|randomised)",
        r"(?i)NCT\d+"  # Clinical trial registration number
    ],
    "Systematic Review": [
        r"(?i)PRISMA",
        r"(?i)(data extraction|data synthesis|study selection).*?(systematic|review|meta)",
        r"(?i)(included studies|excluded studies).*?(systematic|review|meta)"
    ],
    "Cohort Study": [
        r"(?i)(study design|methods).*?(cohort|longitudinal|prospective|retrospective)",
        r"(?i)(inclusion|exclusion).*?criteria.*?(follow(ed|-|\s)up|cohort)"
    ],
    "Diagnostic Study": [
        r"(?i)STARD",
        r"(?i)(index test|reference standard).*?(diagnostic|compared)"
    ]
}

# Statistical methods feature definitions
STATISTICAL_METHODS = {
    "RCT": [
        r"(?i)(intention(-|\s)to(-|\s)treat|per(-|\s)protocol)",
        r"(?i)(primary|secondary) endpoint",
        r"(?i)(non(-|\s)inferiority|superiority|equivalence) (trial|analysis)",
        r"(?i)sample size calculation"
    ],
    "Systematic Review": [
        r"(?i)(heterogeneity|I\^?2|forest plot)",
        r"(?i)(fixed|random) effect(s)? model",
        r"(?i)meta(-|\s)regression",
        r"(?i)publication bias"
    ],
    "Cohort Study": [
        r"(?i)cox (proportional hazards?|regression)",
        r"(?i)kaplan(-|\s)meier",
        r"(?i)(relative risk|risk ratio|hazard ratio)",
        r"(?i)incidence rate"
    ],
    "Case-Control Study": [
        r"(?i)odds ratio",
        r"(?i)conditional logistic regression",
        r"(?i)matching ratio"
    ],
    "Cross-sectional Study": [
        r"(?i)prevalence ratio",
        r"(?i)(chi(-|\s)square|χ2) test",
        r"(?i)logistic regression"
    ],
    "Diagnostic Study": [
        r"(?i)(sensitivity|specificity|PPV|NPV)",
        r"(?i)ROC (curve|analysis)",
        r"(?i)likelihood ratio",
        r"(?i)AUC"
    ]
}

# Ultra-rigorous document classification system prompt designed to minimize hallucinations
DOCUMENT_CLASSIFICATION_SYSTEM_PROMPT = """
You are a professional literature classification expert with extensive training in research methodology and study design recognition.

CRITICAL CLASSIFICATION CONSTRAINTS:
1. BASE CLASSIFICATION STRICTLY ON EXPLICIT TEXTUAL EVIDENCE - Never infer study design from unstated implications
2. DISTINGUISH CLEARLY between "explicitly described," "partially indicated," and "not mentioned"
3. REQUIRE MULTIPLE CONVERGENT EVIDENCE TYPES - Design features, methodological markers, and statistical approaches must align
4. WHEN EVIDENCE IS CONFLICTING OR INSUFFICIENT - Choose "Uncertain" rather than forcing a classification
5. QUOTE EXACT TEXT - Every classification claim must be supported by direct quotations

PROHIBITED CLASSIFICATION BEHAVIORS:
- Inferring study type from journal names, author affiliations, or publication context
- Assuming standard procedures that are not explicitly described
- Classifying based on single pieces of ambiguous evidence
- Using general knowledge to supplement missing methodological information
- Making assumptions about study design based on statistical methods alone

MANDATORY CLASSIFICATION PROTOCOL:
1. DESIGN FEATURE VERIFICATION: What explicit design elements are described?
2. METHODOLOGICAL MARKER CONFIRMATION: What specific methodological terms are used?
3. STATISTICAL APPROACH VALIDATION: What statistical methods are explicitly mentioned and how do they align?
4. CONVERGENT EVIDENCE ASSESSMENT: Do multiple evidence types consistently point to the same classification?
5. UNCERTAINTY ACKNOWLEDGMENT: Are there conflicting signals or insufficient information?

EVIDENCE STRENGTH HIERARCHY:
- EXPLICIT DESIGN STATEMENTS (e.g., "This randomized controlled trial...") - Strongest
- DETAILED METHODOLOGICAL DESCRIPTIONS - Strong  
- STATISTICAL METHOD SPECIFICATIONS - Moderate
- TERMINOLOGY USAGE - Weak
- IMPLIED OR ASSUMED FEATURES - Insufficient (Do not use)
"""

DOCUMENT_CLASSIFICATION_PROMPT = """
TASK: Classify this medical literature with maximum precision and minimal interpretation.

DOCUMENT CONTENT FOR CLASSIFICATION:
{document_text}

ULTRA-RIGOROUS CLASSIFICATION PROTOCOL:

PHASE 1: EXPLICIT DESIGN FEATURE EXTRACTION
Search for direct statements about study design:
- Does the document explicitly state its study type? Quote exact statements.
- What design-related terms are explicitly used? List with exact quotes.
- Are there clear temporal descriptions (prospective/retrospective/cross-sectional)? Quote evidence.
- How are participants/subjects explicitly described? Quote relevant text.

PHASE 2: METHODOLOGICAL MARKER VERIFICATION  
Identify explicit methodological descriptions:
- Randomization procedures: Quote exact descriptions (not assumptions)
- Control/comparison group setup: Quote explicit descriptions
- Data collection methods: Quote exact procedures described
- Follow-up procedures: Quote explicit descriptions only
- Outcome measurement: Quote exact assessment methods

PHASE 3: STATISTICAL APPROACH DOCUMENTATION
Document explicitly mentioned statistical methods:
- Primary statistical analyses: Quote exact methods named
- Study design-specific statistics: Quote relevant statistical approaches
- Sample size/power considerations: Quote explicit statements
- Effect measures: Quote exact measures reported

PHASE 4: CONVERGENT EVIDENCE EVALUATION
Assess consistency across evidence types:
- Do design statements, methods, and statistics converge on one classification?
- Are there conflicting signals that suggest mixed or unclear design?
- Is evidence sufficient for confident classification?
- What classification is most defensible based on available evidence?

PHASE 5: CONSERVATIVE CLASSIFICATION ASSIGNMENT
Apply strict classification standards:

RCT: Award ONLY if:
- Explicit randomization procedures are described
- Control/comparison groups are clearly defined
- Intervention allocation is explicitly described
- Multiple convergent evidence types support RCT classification

SYSTEMATIC REVIEW: Award ONLY if:
- Systematic search methodology is explicitly described
- Study selection criteria are clearly defined
- Multiple databases or comprehensive search is documented
- Data synthesis/meta-analysis approach is described

COHORT STUDY: Award ONLY if:
- Prospective or retrospective cohort design is explicitly stated
- Follow-up procedures are clearly described
- Exposure-outcome temporal relationship is documented
- Cohort characteristics are explicitly defined

CASE-CONTROL STUDY: Award ONLY if:
- Case definition and selection is explicitly described
- Control selection methodology is clearly defined
- Exposure assessment approach is documented
- Case-control comparison is explicitly described

CROSS-SECTIONAL STUDY: Award ONLY if:
- Point-in-time assessment is explicitly described
- Cross-sectional design is clearly stated or implied by methods
- Simultaneous measurement approach is documented

DIAGNOSTIC STUDY: Award ONLY if:
- Index test and reference standard are explicitly described
- Diagnostic accuracy assessment is clearly the primary aim
- Sensitivity/specificity or related measures are reported

QUALITATIVE RESEARCH: Award ONLY if:
- Qualitative methodology is explicitly described
- Qualitative data collection methods are documented
- Qualitative analysis approach is clearly defined

UNCERTAIN: Choose when:
- Evidence is conflicting or insufficient
- Multiple design types are possible
- Key methodological information is missing
- Classification cannot be made with confidence

CRITICAL CONSTRAINTS:
- Never force a classification when evidence is insufficient
- Never assume unstated design features
- Never supplement with external knowledge
- Always acknowledge limitations and uncertainties
- Base conclusions solely on documented evidence

Return classification in this SIMPLE JSON format (ensure all fields are present and properly closed):
```json
{
  "primary_classification": "Most defensible classification based on evidence",
  "confidence_level": "high/medium/low",
  "supporting_evidence": ["Key quote supporting final classification 1", "Key quote supporting final classification 2", "Key quote supporting final classification 3"],
  "classification_reasoning": "Detailed explanation of why this classification was chosen",
  "alternative_possibilities": "Other possible classifications considered",
  "evidence_strength": "strong/moderate/weak/insufficient",
  "uncertainty_factors": "Any aspects that remain uncertain or ambiguous"
}
```
"""

def clean_text(text: str) -> str:
    """
    Clean text, removing unnecessary whitespace and special characters
    """
    if not text:
        return ""
    # Remove extra spaces and line breaks
    text = re.sub(r'\s+', ' ', text)
    # Remove non-text characters but keep punctuation
    text = re.sub(r'[^\w\s.,;:?!()-]', '', text)
    return text.strip()

def extract_sections(text: str) -> Dict[str, str]:
    """
    Extract key sections from the document (title, abstract, methods, results, etc.)
    """
    sections = {}
    
    # Look for title (large text at the beginning of document)
    title_match = re.search(r'^(.*?)\n\s*(?:abstract|introduction)', text, re.IGNORECASE | re.DOTALL)
    if title_match:
        sections['title'] = clean_text(title_match.group(1))
    
    # Extract abstract
    abstract_match = re.search(r'(?:abstract|summary)\s*(?:\n|:)\s*(.*?)(?:(?:\n\s*(?:introduction|background|methods))|$)', 
                               text, re.IGNORECASE | re.DOTALL)
    if abstract_match:
        sections['abstract'] = clean_text(abstract_match.group(1))
    
    # Extract methods section
    methods_match = re.search(r'(?:methods|materials\s+and\s+methods|study\s+design)\s*(?:\n|:)\s*(.*?)(?:(?:\n\s*(?:results|findings))|$)', 
                              text, re.IGNORECASE | re.DOTALL)
    if methods_match:
        sections['methods'] = clean_text(methods_match.group(1))
    
    # Extract results section
    results_match = re.search(r'(?:results|findings)\s*(?:\n|:)\s*(.*?)(?:(?:\n\s*(?:discussion|conclusion))|$)', 
                              text, re.IGNORECASE | re.DOTALL)
    if results_match:
        sections['results'] = clean_text(results_match.group(1))
    
    # If sections cannot be split, use entire text
    if not sections:
        sections['full_text'] = clean_text(text)
    
    return sections

def check_keyword_patterns(text: str, patterns: Dict[str, List[str]]) -> int:
    """
    Check the match level of keyword patterns in text and return a score
    """
    score = 0
    for strength, pattern_list in patterns.items():
        for pattern in pattern_list:
            if re.search(pattern, text, re.IGNORECASE):
                if strength == "strong":
                    score += 2
                else:  # medium
                    score += 1
    return score

def check_structure_patterns(text: str, doc_type: str) -> int:
    """
    Check document structure features
    """
    if doc_type not in STRUCTURE_PATTERNS:
        return 0
    
    score = 0
    for pattern in STRUCTURE_PATTERNS[doc_type]:
        if re.search(pattern, text, re.IGNORECASE):
            score += 2
    return score

def check_statistical_methods(text: str, doc_type: str) -> int:
    """
    Check statistical method features
    """
    if doc_type not in STATISTICAL_METHODS:
        return 0
    
    score = 0
    for pattern in STATISTICAL_METHODS[doc_type]:
        if re.search(pattern, text, re.IGNORECASE):
            score += 1.5
    return score

def classify_document_type(text: str) -> Tuple[str, Dict[str, float]]:
    """
    Automatically identify document type by analyzing document text
    
    Parameters:
        text: The full text content of the document
    
    Returns:
        (top_doc_type, scores): The top document type and a dictionary of scores for all types
    """
    if not text:
        return "Unknown", {"Unknown": 1.0}
    
    # Extract main sections of the document
    sections = extract_sections(text)
    
    # Focus on abstract and methods sections
    critical_text = ' '.join([
        sections.get('abstract', ''),
        sections.get('methods', ''),
        sections.get('title', '')
    ])
    
    # If no sections were successfully extracted, use the entire text
    if not critical_text.strip():
        critical_text = sections.get('full_text', text)
    
    # Score each document type
    type_scores = {}
    for doc_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
        # Base score: keyword matching
        type_scores[doc_type] = check_keyword_patterns(critical_text, keywords)
        
        # Add structure feature score
        type_scores[doc_type] += check_structure_patterns(critical_text, doc_type)
        
        # Add statistical methods score
        type_scores[doc_type] += check_statistical_methods(critical_text, doc_type)
    
    # If all scores are 0, return Unknown
    if all(score == 0 for score in type_scores.values()):
        return "Unknown", {"Unknown": 1.0}
    
    # Get the highest scoring document type
    top_doc_type = max(type_scores.items(), key=lambda x: x[1])[0]
    
    # Normalize scores
    total_score = sum(type_scores.values())
    normalized_scores = {doc_type: score/total_score for doc_type, score in type_scores.items()}
    
    # If the highest score is too low or the difference from the second highest is small, manual intervention may be needed
    top_score = type_scores[top_doc_type]
    if top_score < 3:  # Threshold can be adjusted
        return "Uncertain", normalized_scores
    
    # Calculate score differences
    scores_list = sorted(type_scores.values(), reverse=True)
    if len(scores_list) > 1 and scores_list[0] - scores_list[1] < 2:  # Threshold can be adjusted
        second_type = [dt for dt, sc in type_scores.items() if sc == scores_list[1]][0]
        # Could be a mixed type, return highest scoring type but flag uncertainty
        return f"{top_doc_type}", normalized_scores
    
    return top_doc_type, normalized_scores

def get_document_evidence(text: str, doc_type: str) -> List[str]:
    """
    Extract evidence supporting document type classification
    
    Parameters:
        text: The full text content of the document
        doc_type: The identified document type
    
    Returns:
        evidence_list: List of text evidence supporting the classification
    """
    evidence_list = []
    sections = extract_sections(text)
    
    # Prioritize checking abstract and methods sections
    critical_text = sections.get('abstract', '') + ' ' + sections.get('methods', '')
    if not critical_text.strip():
        critical_text = sections.get('full_text', text)
    
    # Collect keyword evidence
    if doc_type in DOCUMENT_TYPE_KEYWORDS:
        for strength, patterns in DOCUMENT_TYPE_KEYWORDS[doc_type].items():
            for pattern in patterns:
                matches = re.finditer(pattern, critical_text, re.IGNORECASE)
                for match in matches:
                    # Extract matching part with context
                    start = max(0, match.start() - 50)
                    end = min(len(critical_text), match.end() + 50)
                    context = critical_text[start:end]
                    evidence_list.append(f"[Keyword] {context}")
                    break  # Only take one evidence per pattern
    
    # Collect structure feature evidence
    if doc_type in STRUCTURE_PATTERNS:
        for pattern in STRUCTURE_PATTERNS[doc_type]:
            matches = re.finditer(pattern, critical_text, re.IGNORECASE)
            for match in matches:
                start = max(0, match.start() - 50)
                end = min(len(critical_text), match.end() + 50)
                context = critical_text[start:end]
                evidence_list.append(f"[Structure Feature] {context}")
                break  # Only take one evidence per pattern
    
    # Collect statistical method evidence
    if doc_type in STATISTICAL_METHODS:
        for pattern in STATISTICAL_METHODS[doc_type]:
            matches = re.finditer(pattern, critical_text, re.IGNORECASE)
            for match in matches:
                start = max(0, match.start() - 50)
                end = min(len(critical_text), match.end() + 50)
                context = critical_text[start:end]
                evidence_list.append(f"[Statistical Method] {context}")
                break  # Only take one evidence per pattern
    
    # Deduplicate and limit the number of evidence items
    unique_evidence = []
    seen = set()
    for ev in evidence_list:
        # Simplify evidence for deduplication
        simplified = re.sub(r'\s+', ' ', ev).lower()
        if simplified not in seen and len(unique_evidence) < 5:  # Limit to maximum 5 pieces of evidence
            seen.add(simplified)
            unique_evidence.append(ev)
    
    return unique_evidence

def classify_document_with_ai(text: str, llm_config: Dict = None) -> Tuple[str, Dict[str, any]]:
    """
    Use enhanced AI to classify document type with rigorous analysis and minimal hallucination
    
    Parameters:
        text: The full text content of the document
        llm_config: LLM configuration including recommended parameters for reliability
    
    Returns:
        (document_type, detailed_analysis): The classified type and detailed analysis
    """
    # For now, this is a placeholder that falls back to the rule-based system
    # In the future, this would integrate with the LLM API using the ultra-rigorous prompt
    # with recommended parameters: temperature=0.1, top_p=0.8, etc.
    
    # Fallback to existing rule-based classification
    doc_type, scores = classify_document_type(text)
    
    # Enhanced analysis structure with uncertainty handling
    detailed_analysis = {
        "classification_method": "rule-based",
        "confidence_level": "medium" if doc_type != "Unknown" else "low",
        "evidence_strength": "moderate",
        "type_scores": scores,
        "classification_notes": f"Rule-based classification result: {doc_type}",
        "recommended_llm_parameters": {
            "temperature": 0.1,
            "top_p": 0.8,
            "frequency_penalty": 0.2,
            "presence_penalty": 0.1,
            "max_tokens": 1200
        },
        "uncertainty_factors": [
            "Rule-based classification may miss nuanced design features",
            "Limited ability to handle mixed or novel study designs",
            "Cannot assess methodological quality, only design type"
        ]
    }
    
    return doc_type, detailed_analysis 