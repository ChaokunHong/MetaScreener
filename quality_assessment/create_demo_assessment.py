"""
Create a demo assessment for testing the UI

This script creates a sample assessment with completed status and demo results
that can be viewed in the quality assessment results page.

Usage: python -m quality_assessment.create_demo_assessment [type]
Where [type] can be "sr" (Systematic Review), "rct" (RCT), "processing" (In Progress), or "pending" (Pending)
"""

import sys
from quality_assessment.services import _assessments_db, _save_assessments_to_file, _next_assessment_id

def create_demo_assessment(assessment_type="sr"):
    """Create a demo assessment with sample data
    
    Args:
        assessment_type: The type of assessment to create ("sr", "rct", "processing", or "pending")
    """
    global _next_assessment_id
    
    # Create a unique ID for the demo
    demo_id = str(_next_assessment_id)
    _next_assessment_id += 1
    
    if assessment_type.lower() == "rct":
        print(f"Creating RCT demo assessment with ID: {demo_id}")
        create_rct_demo(demo_id)
    elif assessment_type.lower() == "processing":
        print(f"Creating Processing demo assessment with ID: {demo_id}")
        create_processing_demo(demo_id)
    elif assessment_type.lower() == "pending":
        print(f"Creating Pending demo assessment with ID: {demo_id}")
        create_pending_demo(demo_id)
    else:
        print(f"Creating Systematic Review demo assessment with ID: {demo_id}")
        create_sr_demo(demo_id)
    
    # Save to file
    _save_assessments_to_file()
    print(f"Demo assessment created with ID: {demo_id}")
    print(f"View it at: /quality/result/{demo_id}")
    print(f"Simple view: /quality/view_details/{demo_id}")

def create_sr_demo(demo_id):
    """Create a systematic review demo assessment"""
    _assessments_db[demo_id] = {
        "status": "completed",
        "filename": "demo_systematic_review.pdf",
        "document_type": "Systematic Review",
        "text_preview": "This is a sample systematic review document for UI testing purposes...",
        "classification_evidence": [
            "[Keyword] we conducted a systematic review and meta-analysis to evaluate the effectiveness of...",
            "[Structure Feature] Following PRISMA guidelines, we searched PubMed, Embase, and Cochrane databases...",
            "[Statistical Method] The heterogeneity between studies was assessed using I² statistics..."
        ],
        "progress": {
            "current": 5,
            "total": 5,
            "message": "Assessment completed!"
        },
        "assessment_details": [
            {
                "criterion_id": "sr_q1",
                "criterion_text": "Did the research questions and inclusion criteria for the review include the components of PICO?",
                "judgment": "Yes",
                "reason": "The authors clearly specified all PICO components in their research question and inclusion criteria section. Population was adults with type 2 diabetes, intervention was dietary approaches, comparator was standard care or other dietary approaches, and outcomes included HbA1c, fasting glucose, and weight change.",
                "evidence_quotes": [
                    "The research question was: 'What is the effect of dietary interventions on glycemic control (HbA1c, fasting glucose) and weight in adults with type 2 diabetes compared to standard care or other dietary approaches?'",
                    "Inclusion criteria specified: adult participants (P), dietary interventions (I), comparison with standard care or alternative diets (C), and measurement of glycemic control or weight outcomes (O)."
                ]
            },
            {
                "criterion_id": "sr_q2",
                "criterion_text": "Did the report of the review contain an explicit statement that the review methods were established prior to the conduct of the review and did the report justify any significant deviations from the protocol?",
                "judgment": "Partial Yes",
                "reason": "The authors mentioned that a protocol was registered in PROSPERO, but did not provide the registration number. They did not report any deviations from protocol, but it's unclear if there were any.",
                "evidence_quotes": [
                    "A protocol for this systematic review was registered in the PROSPERO database.",
                    "The methods followed those outlined in the protocol with no significant deviations."
                ]
            },
            {
                "criterion_id": "sr_q3",
                "criterion_text": "Did the review authors explain their selection of the study designs for inclusion in the review?",
                "judgment": "Yes",
                "reason": "The authors provided a clear explanation for including only randomized controlled trials, citing the need to reduce bias and establish causality for dietary interventions.",
                "evidence_quotes": [
                    "Only randomized controlled trials were included to minimize bias when assessing the causal effects of dietary interventions on glycemic control.",
                    "Observational studies were excluded due to their inherent limitations in establishing causality for dietary interventions."
                ]
            },
            {
                "criterion_id": "sr_q4",
                "criterion_text": "Did the review authors use a comprehensive literature search strategy?",
                "judgment": "Yes",
                "reason": "The search strategy was comprehensive, including multiple databases, hand-searching of references, and consultation with experts. The authors provided their full search strategy in an appendix.",
                "evidence_quotes": [
                    "Electronic searches were conducted in MEDLINE, Embase, CENTRAL, and CINAHL from inception to March 2023.",
                    "Additional studies were identified through hand-searching reference lists of included studies and relevant reviews, and by consulting experts in the field.",
                    "The complete search strategy for all databases is provided in Appendix 1."
                ]
            },
            {
                "criterion_id": "sr_q5",
                "criterion_text": "Did the review authors perform study selection in duplicate?",
                "judgment": "Yes",
                "reason": "Study selection was performed independently by two reviewers at both title/abstract and full-text screening stages, with disagreements resolved by a third reviewer.",
                "evidence_quotes": [
                    "Two reviewers (AB and CD) independently screened titles and abstracts of all retrieved records.",
                    "Full-text articles were assessed independently by the same two reviewers, and disagreements were resolved by discussion or by consulting a third reviewer (EF)."
                ]
            }
        ]
    }

def create_rct_demo(demo_id):
    """Create an RCT demo assessment"""
    _assessments_db[demo_id] = {
        "status": "completed",
        "filename": "demo_randomized_trial.pdf",
        "document_type": "RCT",
        "text_preview": "This is a sample randomized controlled trial document for UI testing purposes...",
        "classification_evidence": [
            "[Keyword] This was a multicenter, randomized, double-blind, placebo-controlled trial...",
            "[Structure Feature] Eligible patients were randomly assigned in a 1:1 ratio to receive either the active treatment or placebo...",
            "[Statistical Method] Intention-to-treat analysis was performed for the primary endpoint..."
        ],
        "progress": {
            "current": 6,
            "total": 6,
            "message": "Assessment completed!"
        },
        "assessment_details": [
            {
                "criterion_id": "rct_d1_1",
                "criterion_text": "Was the allocation sequence random?",
                "judgment": "Low risk",
                "reason": "The study used computer-generated randomization sequence with permuted blocks, which is an appropriate method for generating a random allocation sequence.",
                "evidence_quotes": [
                    "Randomization was performed using a computer-generated sequence with permuted blocks of varying sizes stratified by study site.",
                    "The randomization sequence was generated by an independent statistician not involved in patient recruitment or assessment."
                ]
            },
            {
                "criterion_id": "rct_d1_2",
                "criterion_text": "Was the allocation sequence concealed until participants were enrolled and assigned to interventions?",
                "judgment": "Low risk",
                "reason": "The study used central allocation via an interactive web-based system that ensured allocation concealment until assignment.",
                "evidence_quotes": [
                    "Treatment allocation was performed centrally via an interactive web-based system after confirmation of eligibility.",
                    "Investigators had no access to the randomization list, ensuring concealment of the allocation sequence."
                ]
            },
            {
                "criterion_id": "rct_d2_1",
                "criterion_text": "Were participants and personnel blind to intervention assignment?",
                "judgment": "Low risk",
                "reason": "The study was double-blind with identical-appearing placebo, and measures were taken to maintain blinding throughout the study.",
                "evidence_quotes": [
                    "Both participants and study personnel were blinded to treatment assignment.",
                    "The active treatment and placebo were identical in appearance, taste, and packaging to ensure blinding."
                ]
            },
            {
                "criterion_id": "rct_d3_1",
                "criterion_text": "Were outcome assessors blind to intervention assignment?",
                "judgment": "Low risk",
                "reason": "The outcome assessors were explicitly stated to be blinded to treatment allocation, and mechanisms were in place to maintain this blinding.",
                "evidence_quotes": [
                    "All outcome assessors remained blinded to treatment allocation throughout the study.",
                    "An independent data monitoring committee reviewed unblinded data while investigators remained blinded."
                ]
            },
            {
                "criterion_id": "rct_d4_1",
                "criterion_text": "Were incomplete outcome data adequately addressed?",
                "judgment": "Some concerns",
                "reason": "While an intention-to-treat analysis was performed, the dropout rate was moderately high (15%) and slightly imbalanced between groups, which could introduce some bias.",
                "evidence_quotes": [
                    "The primary analysis followed the intention-to-treat principle, including all randomized participants.",
                    "Overall, 15% of participants (12% in the treatment group vs. 18% in the placebo group) discontinued the study prematurely."
                ]
            },
            {
                "criterion_id": "rct_d5_1",
                "criterion_text": "Were the study's outcomes reported selectively?",
                "judgment": "Low risk",
                "reason": "The study protocol was registered in advance, and all pre-specified outcomes were reported as planned.",
                "evidence_quotes": [
                    "The trial was registered at ClinicalTrials.gov (NCT01234567) before participant enrollment began.",
                    "All outcomes pre-specified in the protocol were reported in the results section with no evidence of selective reporting."
                ]
            }
        ]
    }

def create_processing_demo(demo_id):
    """Create a demo assessment in 'processing' status to test progress bar"""
    _assessments_db[demo_id] = {
        "status": "processing_assessment",
        "filename": "demo_in_progress.pdf",
        "document_type": "Cohort Study",
        "text_preview": "This is a sample document that is still being processed...",
        "classification_evidence": [
            "[Keyword] This prospective cohort study followed 1,500 patients over a period of 5 years...",
            "[Structure Feature] The cohort was divided into exposed and unexposed groups based on baseline characteristics...",
            "[Statistical Method] Cox proportional hazards regression was used to analyze the data..."
        ],
        "progress": {
            "current": 2,
            "total": 6,
            "message": "Analyzing document quality..."
        },
        # No assessment_details yet since it's still processing
    }

def create_pending_demo(demo_id):
    """Create a demo assessment in 'pending_assessment' status to test waiting message"""
    _assessments_db[demo_id] = {
        "status": "pending_assessment",
        "filename": "demo_waiting_for_assessment.pdf",
        "document_type": "Systematic Review",
        "text_preview": "This is a sample document that is waiting in the queue...",
        "classification_evidence": [
            "[Keyword] systematic review and meta-analysis of randomized controlled trials...",
            "[Structure Feature] This review follows PRISMA guidelines...",
            "[Statistical Method] Meta-analyses were conducted using a random-effects model..."
        ],
        "progress": {
            "current": 0,
            "total": 0,
            "message": "Assessment queued. Waiting to begin processing..."
        },
        # No assessment_details yet since it's still in queue
    }

if __name__ == "__main__":
    # Get assessment type from command line if provided
    assessment_type = sys.argv[1] if len(sys.argv) > 1 else "sr"
    create_demo_assessment(assessment_type) 