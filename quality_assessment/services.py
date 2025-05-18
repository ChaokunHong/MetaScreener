# This file will contain the core business logic for the quality assessment feature.

# We will need to import PDF extraction utilities, LLM interaction functions, etc.
from utils import extract_text_from_pdf
# from llm_integrations import classify_document_type_llm, assess_quality_llm 
# (assuming llm_integrations is a module we might create or use existing from main app)

from config import get_current_llm_config, get_llm_providers_info, get_base_url_for_provider, get_api_key_for_provider
from utils import call_llm_api_raw_content # Using raw content to get JSON
from werkzeug.utils import secure_filename # Added for saving PDF

from flask import session, current_app # <--- IMPORT current_app
import json
import re
from typing import Dict, Optional
import traceback # Added for more detailed error logging in background tasks
from quality_assessment.models import classify_document_type, get_document_evidence
from quality_assessment.prompts import get_assessment_prompt # Import the prompt generator
import os
import pickle
from pathlib import Path
import time

# Placeholder for storing assessment data (in a real app, this would be a database)
_assessments_db = {}
_next_assessment_id = 1

# Define file path for persistent storage
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
ASSESSMENTS_FILE = os.path.join(DATA_DIR, 'assessments.pickle')
# Define directory for storing uploaded PDFs for quality assessment preview
QA_PDF_UPLOAD_DIR = os.path.join(DATA_DIR, 'quality_assessment_pdfs')

# Define cleanup interval (1 hour in seconds)
QA_PDF_CLEANUP_INTERVAL_SECONDS = 60 * 60 

# Create data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)
# Create QA PDF upload directory if it doesn't exist
os.makedirs(QA_PDF_UPLOAD_DIR, exist_ok=True)

def cleanup_old_qa_pdfs():
    """Cleans up PDF files older than QA_PDF_CLEANUP_INTERVAL_SECONDS in QA_PDF_UPLOAD_DIR."""
    now = time.time()
    files_deleted_count = 0
    current_app.logger.info(f"QA_PDF_CLEANUP: Starting cleanup of old PDF files in {QA_PDF_UPLOAD_DIR}.")

    try:
        for filename in os.listdir(QA_PDF_UPLOAD_DIR):
            file_path = os.path.join(QA_PDF_UPLOAD_DIR, filename)
            if os.path.isfile(file_path) and filename.lower().endswith('.pdf'):
                try:
                    file_mod_time = os.path.getmtime(file_path)
                    if (now - file_mod_time) > QA_PDF_CLEANUP_INTERVAL_SECONDS:
                        os.remove(file_path)
                        files_deleted_count += 1
                        current_app.logger.info(f"QA_PDF_CLEANUP: Deleted old PDF: {filename}")
                        
                        # Optional: Update _assessments_db to remove reference to the deleted PDF
                        # This requires parsing assessment_id from filename or iterating _assessments_db
                        # For simplicity, we are not doing this here to avoid loading/saving _assessments_db
                        # frequently by a cleanup task. The preview will just fail if file is gone.
                except OSError as e_remove:
                    current_app.logger.error(f"QA_PDF_CLEANUP: Error deleting file {file_path}: {e_remove}")
                except Exception as e_check:
                    current_app.logger.error(f"QA_PDF_CLEANUP: Error checking file {file_path}: {e_check}")
    except Exception as e_list:
        current_app.logger.error(f"QA_PDF_CLEANUP: Error listing files in {QA_PDF_UPLOAD_DIR}: {e_list}")

    current_app.logger.info(f"QA_PDF_CLEANUP: Finished cleanup. Deleted {files_deleted_count} old PDF files.")

def _save_assessments_to_file(assessment_id_to_log: Optional[str] = None):
    """Save assessment data to file for persistence"""
    try:
        if assessment_id_to_log and assessment_id_to_log in _assessments_db:
            current_assessment_data_to_save = _assessments_db[assessment_id_to_log]
            print(f"SAVE_LOGIC: For {assessment_id_to_log}, status being saved: {current_assessment_data_to_save.get('status')}, details count: {len(current_assessment_data_to_save.get('assessment_details', []))}, summary: {current_assessment_data_to_save.get('summary_negative_findings')}")
        
        with open(ASSESSMENTS_FILE, 'wb') as f:
            pickle.dump((_assessments_db, _next_assessment_id), f)
        print(f"SAVE_LOGIC: Assessment data (potentially including {assessment_id_to_log if assessment_id_to_log else 'N/A'}) saved to {ASSESSMENTS_FILE}")
    except Exception as e:
        print(f"Error saving assessment data: {e}")

def _load_assessments_from_file():
    """Load assessment data from file if available"""
    global _assessments_db, _next_assessment_id
    if os.path.exists(ASSESSMENTS_FILE):
        try:
            with open(ASSESSMENTS_FILE, 'rb') as f:
                loaded_db, next_id = pickle.load(f)
            print(f"LOAD_LOGIC: Loaded {len(loaded_db)} assessments from file.")
            # Log details for a specific ID if needed, or for all
            for loaded_id, loaded_data_item in loaded_db.items():
                print(f"LOAD_LOGIC: For loaded ID {loaded_id}, status: {loaded_data_item.get('status')}, details count: {len(loaded_data_item.get('assessment_details', []))}")
            _assessments_db = loaded_db
            _next_assessment_id = next_id
        except Exception as e:
            print(f"Error loading assessment data from file: {e}")
    else:
        print("LOAD_LOGIC: Assessments file not found, starting with empty DB.")

# Load assessments data at module import time
_load_assessments_from_file()
print(f"Initial _assessments_db keys after load: {list(_assessments_db.keys())}") # Log keys after initial load

# --- START: Define Quality Assessment Criteria --- #

# Define known quality assessment tools and their items
# This is a simplified example. In a real system, this could be more detailed
# and potentially loaded from a configuration file or database.
QUALITY_ASSESSMENT_TOOLS = {
    "Systematic Review": {
        "tool_name": "AMSTAR 2",
        "criteria": [
            {"id": "sr_q1", "text": "Did the research questions and inclusion criteria for the review include the components of PICO?", "guidance": "PICO: Population, Intervention, Comparator, Outcome"},
            {"id": "sr_q2", "text": "Did the report of the review contain an explicit statement that the review methods were established prior to the conduct of the review and did the report justify any significant deviations from the protocol?", "guidance": "Look for mention of a protocol (e.g., PROSPERO registration, published protocol)."},
            {"id": "sr_q3", "text": "Did the review authors explain their selection of the study designs for inclusion in the review?", "guidance": "Consider if reasons are given for why certain study designs were included or excluded."},
            {"id": "sr_q4", "text": "Did the review authors use a comprehensive literature search strategy?", "guidance": "At least two databases, reference list searching, keywords and/or MeSH terms."},
            {"id": "sr_q5", "text": "Did the review authors perform study selection in duplicate?", "guidance": "Look for mention of two independent reviewers for study selection."},
            {"id": "sr_q6", "text": "Did the review authors perform data extraction in duplicate?", "guidance": "Look for mention of two independent reviewers for data extraction."},
            {"id": "sr_q7", "text": "Did the review authors provide a list of excluded studies and justify the exclusions?", "guidance": "Check if a list of excluded studies with reasons is provided."},
            {"id": "sr_q8", "text": "Did the review authors describe the included studies in adequate detail?", "guidance": "Look for PICO, research design, timeframe, funding sources."},
            {"id": "sr_q9", "text": "Did the review authors use a satisfactory technique for assessing risk of bias (RoB) in individual studies?", "guidance": "Look for appropriate RoB assessment tools (e.g., Cochrane RoB, ROBINS-I)."},
            {"id": "sr_q10", "text": "Did the review authors report sources of funding for individual studies?", "guidance": "Check if funding for included studies is reported."},
            {"id": "sr_q11", "text": "If meta-analysis was performed, did the authors use appropriate methods for statistical combination of results?", "guidance": "Check if appropriate combination method based on study similarity (fixed/random effects)."},
            {"id": "sr_q12", "text": "If meta-analysis was performed, did the authors assess the potential impact of RoB on the results?", "guidance": "Look for sensitivity analysis or impact discussion based on study quality."},
            {"id": "sr_q13", "text": "Did the authors account for RoB when interpreting/discussing results?", "guidance": "Check if study quality is considered in conclusions."},
            {"id": "sr_q14", "text": "Did the review authors provide a satisfactory explanation for and discussion of heterogeneity observed in the results?", "guidance": "Look for discussion of I² statistic, subgroup analyses, or meta-regression."},
            {"id": "sr_q15", "text": "If quantitative synthesis was performed, did the review authors investigate publication bias and discuss its potential impact?", "guidance": "Check for funnel plot, Egger's test, or other methods."},
            {"id": "sr_q16", "text": "Did the review authors report potential sources of conflict of interest, including funding?", "guidance": "Look for conflict of interest and funding statements."}
        ]
    },
    "RCT": {
        "tool_name": "Cochrane RoB 2",
        "criteria": [
            # Domain 1: Randomization process
            {"id": "rct_d1_1", "text": "1.1 Was the allocation sequence random?", "domain": "D1: Randomization process", 
             "guidance": "Look for description of random component in sequence generation (e.g., random number table, computer random number generator, coin tossing)."},
            {"id": "rct_d1_2", "text": "1.2 Was the allocation sequence concealed until participants were enrolled and assigned to interventions?", "domain": "D1: Randomization process", 
             "guidance": "Check if allocation was concealed by methods like central allocation, sequentially numbered sealed opaque envelopes."},
            {"id": "rct_d1_3", "text": "1.3 Did baseline differences between intervention groups suggest a problem with the randomization process?", "domain": "D1: Randomization process", 
             "guidance": "Examine if baseline characteristics are balanced between groups. Minor differences are expected by chance."},

            # Domain 2: Deviations from intended interventions
            {"id": "rct_d2_1", "text": "2.1 Were participants aware of their assigned intervention during the trial?", "domain": "D2: Deviations from intended interventions", 
             "guidance": "Check if participants were blinded to intervention assignment (also called 'masking')."},
            {"id": "rct_d2_2", "text": "2.2 Were carers and trial personnel aware of participants' assigned intervention during the trial?", "domain": "D2: Deviations from intended interventions", 
             "guidance": "Check if healthcare providers, researchers and other personnel were blinded to intervention assignment."},
            {"id": "rct_d2_3", "text": "2.3 If Y/PY/NI to 2.1 or 2.2: Were there deviations from the intended intervention beyond what would be expected in usual practice?", "domain": "D2: Deviations from intended interventions", 
             "guidance": "Look for deviations from protocol or implementation problems beyond what would occur in routine care."},
            {"id": "rct_d2_4", "text": "2.4 If Y/PY/NI to 2.3: Were these deviations likely to have affected the outcome?", "domain": "D2: Deviations from intended interventions", 
             "guidance": "Consider if the deviations were substantial enough to impact the measured outcomes."},
            {"id": "rct_d2_5", "text": "2.5 Were any participants analyzed in a group different from the one to which they were assigned?", "domain": "D2: Deviations from intended interventions", 
             "guidance": "Check if intention-to-treat (ITT) analysis was used. Look for participants being analyzed according to original assignment regardless of adherence."},
            {"id": "rct_d2_6", "text": "2.6 If Y/PY/NI to 2.5: Was there potential for a substantial impact on the result?", "domain": "D2: Deviations from intended interventions", 
             "guidance": "Consider if the number of participants analyzed in the wrong group could substantially affect results."},

            # Domain 3: Missing outcome data
            {"id": "rct_d3_1", "text": "3.1 Were outcome data available for all, or nearly all, participants randomized?", "domain": "D3: Missing outcome data", 
             "guidance": "Check completion rates. Look for <5% missing data for low risk, or 5-20% with appropriate imputation methods."},
            {"id": "rct_d3_2", "text": "3.2 If N/PN/NI to 3.1: Is there evidence that the result was not biased by missing outcome data?", "domain": "D3: Missing outcome data", 
             "guidance": "Look for sensitivity analyses showing robustness of results to different assumptions about missing data."},
            {"id": "rct_d3_3", "text": "3.3 If N/PN to 3.2: Could missingness in the outcome depend on its true value?", "domain": "D3: Missing outcome data", 
             "guidance": "Consider if participants might have dropped out due to poor outcomes or side effects related to the outcome being measured."},
            {"id": "rct_d3_4", "text": "3.4 If Y/PY/NI to 3.3: Is it likely that missingness in the outcome depended on its true value?", "domain": "D3: Missing outcome data", 
             "guidance": "Assess if there is strong evidence that missing data is related to the actual outcomes that would have been observed."},

            # Domain 4: Measurement of the outcome
            {"id": "rct_d4_1", "text": "4.1 Was the method of measuring the outcome inappropriate?", "domain": "D4: Measurement of the outcome", 
             "guidance": "Check if outcome measures are validated, appropriate for the construct being measured, and used correctly."},
            {"id": "rct_d4_2", "text": "4.2 Could measurement or ascertainment of the outcome have differed between intervention groups?", "domain": "D4: Measurement of the outcome", 
             "guidance": "Determine if the same methods and thresholds were used for outcome assessment in all groups."},
            {"id": "rct_d4_3", "text": "4.3 Were outcome assessors aware of the intervention received by study participants?", "domain": "D4: Measurement of the outcome", 
             "guidance": "Check if those measuring outcomes were blinded to intervention assignment."},
            {"id": "rct_d4_4", "text": "4.4 If Y/PY/NI to 4.3: Could assessment of the outcome have been influenced by knowledge of intervention received?", "domain": "D4: Measurement of the outcome", 
             "guidance": "Consider if the outcome is subjective and could be influenced by knowing the intervention (e.g., pain scales vs. mortality)."},
            {"id": "rct_d4_5", "text": "4.5 If Y/PY/NI to 4.4: Is it likely that assessment of the outcome was influenced by knowledge of intervention received?", "domain": "D4: Measurement of the outcome", 
             "guidance": "Assess the degree to which outcome measurement could have been biased by lack of blinding."},

            # Domain 5: Selection of the reported result
            {"id": "rct_d5_1", "text": "5.1 Were the data that produced this result analyzed in accordance with a pre-specified analysis plan?", "domain": "D5: Selection of the reported result", 
             "guidance": "Check for a pre-registered protocol or statistical analysis plan and if analyses followed it."},
            {"id": "rct_d5_2", "text": "5.2 Is the numerical result being assessed likely to have been selected, on the basis of the results, from multiple outcome measurements?", "domain": "D5: Selection of the reported result", 
             "guidance": "Look for multiple ways of measuring outcomes (e.g., different scales, time points) with selective reporting of favorable results."},
            {"id": "rct_d5_3", "text": "5.3 Is the numerical result being assessed likely to have been selected, on the basis of the results, from multiple analyses of the data?", "domain": "D5: Selection of the reported result", 
             "guidance": "Check for evidence of multiple analyses (subgroups, adjustments, statistical methods) with selective reporting of favorable results."}
        ]
    },
    "Diagnostic Study": {
        "tool_name": "QUADAS-2",
        "criteria": [
            # Domain 1: Patient Selection
            {"id": "ds_d1_1", "text": "1.1 Was a consecutive or random sample of patients enrolled? (Risk of Bias)", "domain": "D1: Patient Selection", 
             "guidance": "Check if patients were selected consecutively or randomly to avoid selection bias."},
            {"id": "ds_d1_2", "text": "1.2 Was a case-control design avoided? (Risk of Bias)", "domain": "D1: Patient Selection", 
             "guidance": "Case-control designs are prone to bias for diagnostic accuracy studies. Check if the study enrolled patients with and without the target condition based on the reference standard."},
            {"id": "ds_d1_3", "text": "1.3 Did the study avoid inappropriate exclusions? (Risk of Bias)", "domain": "D1: Patient Selection", 
             "guidance": "Check if exclusions were appropriate and didn't systematically remove difficult-to-diagnose cases."},
            {"id": "ds_d1_4", "text": "1.4 Are there concerns that the included patients do not match the review question? (Applicability)", "domain": "D1: Patient Selection", 
             "guidance": "Assess if the study population matches the patients who would receive the test in practice."},

            # Domain 2: Index Test
            {"id": "ds_d2_1", "text": "2.1 Were the index test results interpreted without knowledge of the reference standard results? (Risk of Bias)", "domain": "D2: Index Test", 
             "guidance": "Check if those interpreting the index test were blinded to the reference standard results."},
            {"id": "ds_d2_2", "text": "2.2 If a threshold was used, was it pre-specified? (Risk of Bias)", "domain": "D2: Index Test", 
             "guidance": "For tests with numerical results, thresholds should be defined before analyzing results."},
            {"id": "ds_d2_3", "text": "2.3 Are there concerns that the index test, its conduct, or interpretation differ from the review question? (Applicability)", "domain": "D2: Index Test", 
             "guidance": "Assess if the index test was performed and interpreted as it would be in clinical practice."},

            # Domain 3: Reference Standard
            {"id": "ds_d3_1", "text": "3.1 Is the reference standard likely to correctly classify the target condition? (Risk of Bias)", "domain": "D3: Reference Standard", 
             "guidance": "Check if the reference standard is considered the best available method for identifying the target condition."},
            {"id": "ds_d3_2", "text": "3.2 Were the reference standard results interpreted without knowledge of the index test results? (Risk of Bias)", "domain": "D3: Reference Standard", 
             "guidance": "Check if those interpreting the reference standard were blinded to the index test results."},
            {"id": "ds_d3_3", "text": "3.3 Are there concerns that the target condition as defined by the reference standard does not match the review question? (Applicability)", "domain": "D3: Reference Standard", 
             "guidance": "Assess if the reference standard targets the same condition as that being questioned in clinical practice."},

            # Domain 4: Flow and Timing
            {"id": "ds_d4_1", "text": "4.1 Was there an appropriate interval between the index test and reference standard? (Risk of Bias)", "domain": "D4: Flow and Timing", 
             "guidance": "Check if the time between tests was short enough that the condition would not change between assessments."},
            {"id": "ds_d4_2", "text": "4.2 Did all patients receive a reference standard? (Risk of Bias)", "domain": "D4: Flow and Timing", 
             "guidance": "All patients should receive verification of their disease status using the reference standard."},
            {"id": "ds_d4_3", "text": "4.3 Did all patients receive the same reference standard? (Risk of Bias)", "domain": "D4: Flow and Timing", 
             "guidance": "Differential verification (using different reference standards for different patients) can introduce bias."},
            {"id": "ds_d4_4", "text": "4.4 Were all patients included in the analysis? (Risk of Bias)", "domain": "D4: Flow and Timing", 
             "guidance": "Check for unaccounted patients or inappropriate exclusions from analysis."}
        ]
    },
    "Cohort Study": {
        "tool_name": "Newcastle-Ottawa Scale (NOS) for Cohort Studies",
        "criteria": [
            {
                "id": "cs_s1", 
                "text": "S1: How representative was the exposed cohort?", 
                "category": "Selection", 
                "max_points": 1, 
                "guidance": """
                Assess representativeness:
                a) Truly representative of the average exposed person in the community (e.g., all subjects from a defined population like a specific geographical area or a complete register)? (Award a star)
                b) Somewhat representative of the average exposed person in the community (e.g., selected from a clinic, hospital, specific patient group, but not an unselected series from the community)? (Award a star)
                c) Selected group of users (e.g., volunteers, university students, specific professional group)? (No star)
                d) No description of the derivation of the cohort? (No star)
                Justify your choice based on the text and state if a star should be awarded.
                """
            },
            {
                "id": "cs_s2", 
                "text": "S2: How was the non-exposed cohort selected?", 
                "category": "Selection", 
                "max_points": 1, 
                "guidance": """
                Assess selection of the non-exposed cohort:
                a) Drawn from the same community as the exposed cohort (e.g., same geographical area, same source population)? (Award a star)
                b) Drawn from a different source? (No star)
                c) No description of the derivation of the non-exposed cohort? (No star)
                Justify your choice based on the text and state if a star should be awarded.
                """
            },
            {
                "id": "cs_s3", 
                "text": "S3: How was exposure ascertained?", 
                "category": "Selection", 
                "max_points": 1, 
                "guidance": """
                Assess ascertainment of exposure:
                a) Secure record (e.g., surgical records, medical records, official registers)? (Award a star)
                b) Structured interview or questionnaire administered by trained personnel? (Award a star)
                c) Written self-report or mailed questionnaire? (No star for self-report unless validated)
                d) No description? (No star)
                Consider if exposure was validated. Justify your choice and state if a star should be awarded.
                """
            },
            {
                "id": "cs_s4", 
                "text": "S4: Was the outcome of interest not present at the start of the study?", 
                "category": "Selection", 
                "max_points": 1, 
                "guidance": """
                Confirm outcome was not present at baseline:
                a) Yes, explicitly stated or clear from study design (e.g., incident cases in a prospective cohort). (Award a star)
                b) No, or unclear if outcome was present at start. (No star)
                Justify your choice based on the text and state if a star should be awarded.
                """
            },
            {
                "id": "cs_c1", 
                "text": "C1: Were the cohorts comparable on the basis of design or analysis, controlling for confounders?", 
                "category": "Comparability", 
                "max_points": 2, 
                "guidance": """
                Assess comparability by controlling for confounders:
                - A study can be awarded a maximum of two stars in this section. 
                - One star if cohorts are controlled for the most important confounder (e.g., age).
                - An additional star if cohorts are controlled for any other key confounders (e.g., sex, smoking status, SES, specify which ones).
                State which confounders were controlled for and award 0, 1, or 2 stars with justification.
                """
            },
            {
                "id": "cs_o1", 
                "text": "O1: How was the outcome assessed?", 
                "category": "Outcome", 
                "max_points": 1, 
                "guidance": """
                Assess method of outcome assessment:
                a) Independent blind assessment (e.g., two independent assessors, or one assessor blinded to exposure status)? (Award a star)
                b) Record linkage (e.g., to official registers like death or cancer registries)? (Award a star)
                c) Self-report (unless validated, usually no star)? (No star if unvalidated)
                d) No description? (No star)
                Justify your choice and state if a star should be awarded.
                """
            },
            {
                "id": "cs_o2", 
                "text": "O2: Was the follow-up long enough for outcomes to occur?", 
                "category": "Outcome", 
                "max_points": 1, 
                "guidance": """
                Assess adequacy of follow-up duration:
                a) Yes, follow-up duration is clearly stated and sufficient for the outcome of interest to occur (e.g., >5 years for many chronic diseases, or average follow-up time reported and appropriate). (Award a star)
                b) No, follow-up too short or not described. (No star)
                Justify your choice and state if a star should be awarded.
                """
            },
            {
                "id": "cs_o3", 
                "text": "O3: Was the follow-up adequate (i.e., completeness)?", 
                "category": "Outcome", 
                "max_points": 1, 
                "guidance": """
                Assess adequacy/completeness of follow-up:
                a) Complete follow-up (e.g., all subjects accounted for, or >80-90% follow-up depending on study duration/outcome)? (Award a star)
                b) Subjects lost to follow-up unlikely to introduce bias (e.g., loss to follow-up <20% AND description of those lost shows no significant difference from those followed, or reasons for loss are unrelated to outcome)? (Award a star)
                c) Follow-up rate <80% (or high loss to follow-up without adequate description/justification) or no statement about follow-up. (No star)
                Justify your choice and state if a star should be awarded.
                """
            }
        ]
    },
    "Case-Control Study": {
        "tool_name": "Newcastle-Ottawa Scale (NOS) for Case-Control Studies",
        "criteria": [
            {
                "id": "ccs_s1", 
                "text": "S1: Is the case definition adequate?", 
                "category": "Selection", 
                "max_points": 1, 
                "guidance": """
                Assess case definition:
                a) Yes, with independent validation (e.g., > 1 person/record/time/process to extract information, or reference to primary record source such as medical/hospital records)? (Award a star)
                b) Yes, e.g., record linkage or based on self-reports with no reference to primary record? (No star)
                c) No description? (No star)
                Justify your choice based on the text and state if a star should be awarded.
                """
            },
            {
                "id": "ccs_s2", 
                "text": "S2: Representativeness of the cases", 
                "category": "Selection", 
                "max_points": 1, 
                "guidance": """
                Assess representativeness of cases:
                a) Consecutive or obviously representative series of cases (e.g., all cases in a defined catchment area or time period)? (Award a star)
                b) Potential for selection biases or not stated? (No star)
                Justify your choice based on the text and state if a star should be awarded.
                """
            },
            {
                "id": "ccs_s3", 
                "text": "S3: Selection of Controls", 
                "category": "Selection", 
                "max_points": 1, 
                "guidance": """
                Assess control selection:
                a) Community controls (same community as cases and would have been cases if had disease)? (Award a star)
                b) Hospital controls (same community as cases, within same hospital)? (Award a star)
                c) No description/ other? (No star)
                Justify your choice and state if a star should be awarded.
                """
            },
            {
                "id": "ccs_s4", 
                "text": "S4: Definition of Controls", 
                "category": "Selection", 
                "max_points": 1, 
                "guidance": """
                Assess definition of controls:
                a) No history of disease (outcome of interest)? (Award a star)
                b) No description of source? (No star)
                Justify your choice based on the text and state if a star should be awarded.
                """
            },
            {
                "id": "ccs_c1", 
                "text": "C1: Comparability of cases and controls on the basis of the design or analysis", 
                "category": "Comparability", 
                "max_points": 2, 
                "guidance": """
                Assess comparability of cases and controls:
                - A study can be awarded a maximum of two stars in this section. 
                - One star if cases and controls are matched or adjusted for the most important confounder (e.g., age).
                - An additional star if cases and controls are matched or adjusted for any additional important confounders (e.g., sex, ethnicity, socioeconomic factors).
                State which confounders were controlled for and award 0, 1, or 2 stars with justification.
                """
            },
            {
                "id": "ccs_e1", 
                "text": "E1: Ascertainment of exposure", 
                "category": "Exposure", 
                "max_points": 1, 
                "guidance": """
                Assess quality of exposure ascertainment:
                a) Secure record (e.g., surgical records, medical records, employment records)? (Award a star)
                b) Structured interview where blind to case/control status? (Award a star)
                c) Interview not blinded to case/control status? (No star)
                d) Written self-report or medical record only? (No star)
                e) No description? (No star)
                Justify your choice and state if a star should be awarded.
                """
            },
            {
                "id": "ccs_e2", 
                "text": "E2: Same method of ascertainment for cases and controls", 
                "category": "Exposure", 
                "max_points": 1, 
                "guidance": """
                Assess if same method was used for both groups:
                a) Yes (Award a star)
                b) No (No star)
                Justify your choice and state if a star should be awarded.
                """
            },
            {
                "id": "ccs_e3", 
                "text": "E3: Non-Response rate", 
                "category": "Exposure", 
                "max_points": 1, 
                "guidance": """
                Assess completeness of data collection:
                a) Same rate for both groups (Award a star)
                b) Non-respondents described (Award a star)
                c) Rate different and no designation (No star)
                Justify your choice and state if a star should be awarded.
                """
            }
        ]
    },
    "Cross-sectional Study": {
        "tool_name": "AXIS Tool for Cross-sectional Studies",
        "criteria": [
            {
                "id": "css_1",
                "text": "Were the aims/objectives of the study clear?",
                "guidance": "Check if the authors clearly state what they aimed to research or find."
            },
            {
                "id": "css_2",
                "text": "Was the study design appropriate for the stated aim(s)?",
                "guidance": "Is a cross-sectional study the right type of study to address the aims?"
            },
            {
                "id": "css_3",
                "text": "Was the sample size justified?",
                "guidance": "Did the authors justify their chosen sample size (e.g., power calculation)?"
            },
            {
                "id": "css_4",
                "text": "Was the target/reference population clearly defined?",
                "guidance": "Is it clear who the research is about? (e.g., all adults over 18 in Spain)"
            },
            {
                "id": "css_5",
                "text": "Was the sample frame taken from an appropriate population base so that it closely represented the target/reference population?",
                "guidance": "Did the researchers use a suitable population that would accurately represent their target group?"
            },
            {
                "id": "css_6",
                "text": "Was the selection process likely to select subjects/participants that were representative of the target/reference population?",
                "guidance": "Did the authors select people from the sample frame in a way that ensured they were representative of the target population?"
            },
            {
                "id": "css_7",
                "text": "Were measures undertaken to address and categorize non-responders?",
                "guidance": "Did the authors describe what they did about people who didn't respond or participate?"
            },
            {
                "id": "css_8",
                "text": "Were the risk factor and outcome variables measured appropriate to the aims of the study?",
                "guidance": "Did the researchers measure the right things according to what they wanted to study?"
            },
            {
                "id": "css_9",
                "text": "Were the risk factor and outcome variables measured correctly using instruments/measurements that had been trialled, piloted or published previously?",
                "guidance": "Did they use reliable and validated methods/instruments to measure their variables?"
            },
            {
                "id": "css_10",
                "text": "Is it clear what was used to determine statistical significance and/or precision estimates?",
                "guidance": "Did the authors clearly describe the statistical methods they used to determine significance?"
            }
        ]
    },
    "Qualitative Research": {
        "tool_name": "CASP Qualitative Research Checklist",
        "criteria": [
            {
                "id": "qr_1",
                "text": "Was there a clear statement of the aims of the research?",
                "guidance": "Consider: what the goal of the research was, why it is important, and its relevance."
            },
            {
                "id": "qr_2",
                "text": "Is a qualitative methodology appropriate?",
                "guidance": "Consider: if the research seeks to interpret or illuminate the actions and/or subjective experiences of research participants."
            },
            {
                "id": "qr_3",
                "text": "Was the research design appropriate to address the aims of the research?",
                "guidance": "Consider: if the researcher has justified the research design (e.g., discussed how they decided which methods to use)."
            },
            {
                "id": "qr_4",
                "text": "Was the recruitment strategy appropriate to the aims of the research?",
                "guidance": "Consider: if the researcher explained how participants were selected and why these participants were appropriate."
            },
            {
                "id": "qr_5",
                "text": "Were the data collected in a way that addressed the research issue?",
                "guidance": "Consider: if the setting for data collection was justified, if it's clear how data were collected, if the researcher has justified the methods chosen, and if methods were modified during the study."
            },
            {
                "id": "qr_6",
                "text": "Has the relationship between researcher and participants been adequately considered?",
                "guidance": "Consider: if the researcher critically examined their own role, potential bias and influence during formulation of research questions, data collection, and analysis and selection of data."
            },
            {
                "id": "qr_7",
                "text": "Have ethical issues been taken into consideration?",
                "guidance": "Consider: if there are sufficient details of how the research was explained to participants, if ethical standards were maintained, and if issues of informed consent and confidentiality were discussed."
            },
            {
                "id": "qr_8",
                "text": "Was the data analysis sufficiently rigorous?",
                "guidance": "Consider: if there is an in-depth description of the analysis process, if thematic analysis was used (if so, is it clear how categories/themes were derived), and if the researcher explains how the data presented were selected."
            },
            {
                "id": "qr_9",
                "text": "Is there a clear statement of findings?",
                "guidance": "Consider: if the findings are explicit, if there is adequate discussion of the evidence both for and against the researcher's arguments, and if the researcher has discussed the credibility of their findings."
            },
            {
                "id": "qr_10",
                "text": "How valuable is the research?",
                "guidance": "Consider: if the researcher discusses the contribution the study makes to existing knowledge or understanding, if they identify new areas where research is necessary, and if they discuss how the findings can be transferred to other populations."
            }
        ]
    },
    "Economic Evaluation": {
        "tool_name": "CHEERS 2022",
        "criteria": [
            {"id": "ee_1", "text": "Was the study identified as an economic evaluation or use terms like cost-effectiveness?", 
             "guidance": "Look for clear identification in title or abstract that this is an economic evaluation. Terms like cost-effectiveness, cost-benefit, or economic analysis should be present."},
            {"id": "ee_2", "text": "Is there a structured abstract that includes context, setting, methods, results, and implications?", 
             "guidance": "Check if the abstract contains these key components: context/background, study objectives, methods (perspective, time horizon, interventions, outcomes, etc.), results (costs, effects, incremental costs and effects), and implications for decision-making."},
            {"id": "ee_3", "text": "Does the introduction describe what is already known and relevance to decision-makers?", 
             "guidance": "The introduction should clearly explain the economic importance of the question, background on existing evidence, and why the study is needed for decision-making in the relevant context."},
            {"id": "ee_4", "text": "Are target populations and subgroups clearly described?", 
             "guidance": "Check if the study clearly defines the characteristics of the population(s) being analyzed, including any relevant demographic, clinical, or socioeconomic factors. Subgroup analyses should be explained if conducted."},
            {"id": "ee_5", "text": "Are the setting and location relevant for the research question?", 
             "guidance": "The healthcare setting (primary care, hospital, community), geographical location, and relevant characteristics of the healthcare system should be described and appropriate for the decision problem."},
            {"id": "ee_6", "text": "Is the perspective of the study stated and justified?", 
             "guidance": "The study should explicitly state which perspective was used (e.g., healthcare system, societal, payer, provider, patient) and justify why this perspective is appropriate for the research question."},
            {"id": "ee_7", "text": "Are the interventions/strategies being compared clearly described?", 
             "guidance": "All compared interventions should be described in sufficient detail to allow readers to understand exactly what is being compared. This includes standard care or 'do nothing' comparators."},
            {"id": "ee_8", "text": "Is the time horizon appropriate and explained?", 
             "guidance": "The time horizon should be long enough to capture all important differences in costs and outcomes between alternatives. Lifetime horizons are often appropriate for chronic conditions. The choice should be justified."},
            {"id": "ee_9", "text": "Is the discount rate for costs and outcomes stated and justified?", 
             "guidance": "For studies with time horizons longer than one year, future costs and outcomes should be discounted. The rate should be stated (typically 3-5%) and justified if different from standard rates in the setting."},
            {"id": "ee_10", "text": "Are the outcomes clearly stated and relevant to the research question?", 
             "guidance": "Economic evaluations should clearly state primary and secondary outcomes used. For cost-utility analyses, check if quality-adjusted life years (QALYs) or similar measures are used. Outcomes should be relevant to the decision problem."},
            {"id": "ee_11", "text": "Are economic evaluation methods described and appropriate?", 
             "guidance": "Check if the specific form of economic evaluation is described (cost-utility, cost-effectiveness, cost-benefit, cost-minimization). The methods should be appropriate for the research question and outcomes."},
            {"id": "ee_12", "text": "Is uncertainty addressed through sensitivity analysis?", 
             "guidance": "Look for deterministic and/or probabilistic sensitivity analyses that explore how results change when key parameters vary. Important assumptions should be tested through scenario analyses."},
            {"id": "ee_13", "text": "Are incremental costs and outcomes reported?", 
             "guidance": "Results should include both absolute and incremental costs and outcomes for all alternatives. The incremental cost-effectiveness ratio (ICER) should be calculated for the primary analysis."},
            {"id": "ee_14", "text": "Are characterizations of uncertainty and heterogeneity provided?", 
             "guidance": "Check if the uncertainty around the main results is quantified (e.g., confidence intervals, cost-effectiveness acceptability curves). Heterogeneity across subgroups should be explored if relevant."},
            {"id": "ee_15", "text": "Does the discussion address the study limitations and generalizability?", 
             "guidance": "Look for an honest discussion of key limitations, potential biases, and how they might affect interpretation. The discussion should address generalizability to other settings or populations."},
            {"id": "ee_16", "text": "Are sources of funding and conflicts of interest declared?", 
             "guidance": "Check if funding sources are disclosed and potential conflicts of interest for all authors are declared. The role of funders in the study should be described."}
        ]
    },
    "Animal Research": {
        "tool_name": "ARRIVE 2.0 Guidelines",
        "criteria": [
            {"id": "ar_1", "text": "Study design: Are specific objectives stated and primary/secondary outcomes defined?",
             "guidance": "Check if the study has clear objectives, hypotheses where appropriate, and well-defined primary and secondary outcomes. Exploratory outcomes should be distinguished from confirmatory testing."},
            {"id": "ar_2", "text": "Sample size: Was sample size determined and explained?",
             "guidance": "Examine if the study explains how the number of animals was determined, including statistical power calculations where appropriate. If formal sample size calculations weren't performed, this should be stated."},
            {"id": "ar_3", "text": "Inclusion and exclusion criteria: Are clear criteria defined?",
             "guidance": "Check if the study describes inclusion and exclusion criteria for animals at each stage of the experiment, including criteria for removing animals during the study and whether any animals or data were excluded from analysis."},
            {"id": "ar_4", "text": "Randomization: Was allocation to groups done randomly?",
             "guidance": "Assess if the study describes the method of randomization, including any stratification factors. If randomization wasn't used, the study should state this and explain why."},
            {"id": "ar_5", "text": "Blinding: Were investigators blinded during experiment and analysis?",
             "guidance": "Check if the study describes who was blinded (e.g., investigators, caregivers, outcome assessors) and how blinding was maintained. If blinding wasn't performed, this should be stated with reasons."},
            {"id": "ar_6", "text": "Animal characteristics: Are species, strain, sex, age, and weight described?",
             "guidance": "Evaluate if the study provides detailed characteristics including species, strain, substrain, genetic background, sex, age range, and weight range. Source of animals and relevant permits should be included."},
            {"id": "ar_7", "text": "Housing and husbandry: Are conditions properly described?",
             "guidance": "Check if housing (type of facility, cage/housing type, material, group size), husbandry conditions (lighting, temperature, access to food and water), and environmental enrichment are described."},
            {"id": "ar_8", "text": "Experimental procedures: Are procedures described in sufficient detail?",
             "guidance": "Assess if procedures are described with sufficient detail to allow others to replicate them. This includes anesthesia/analgesia methods, surgical procedures, experimental protocols, and humane endpoints."},
            {"id": "ar_9", "text": "Results: Are results clearly reported for each analysis with precision measures?",
             "guidance": "Check if results are reported for each analysis with a measure of precision (e.g., standard error, confidence interval) and the statistical method used. Both raw and adjusted results should be available where applicable."},
            {"id": "ar_10", "text": "Adverse events: Are adverse events reported?",
             "guidance": "Evaluate if the study reports details of all important adverse events. This includes unexpected outcomes, deaths, protocol modifications, or interventions required to improve animal welfare."},
            {"id": "ar_11", "text": "Ethics statement: Does the study include an ethics statement?",
             "guidance": "Check if the study provides details of ethical review permissions, relevant licenses, and national or institutional guidelines for the care and use of animals."},
            {"id": "ar_12", "text": "Declaration of interests: Are funding sources and conflicts of interest declared?",
             "guidance": "Assess if the study declares all potential conflicts of interest, including financial and non-financial interests. Sources of funding and the role of funders should be clearly stated."},
            {"id": "ar_13", "text": "Data access: Is there information on data accessibility?",
             "guidance": "Check if the study provides a statement on whether and where data supporting the results are available, or explains any restrictions to data availability."},
            {"id": "ar_14", "text": "Translation: Does the study discuss implications for human biology or medicine?",
             "guidance": "For studies with potential translational applications, assess if the study discusses how the findings inform human biology or medicine and any limitations in translating the findings."}
        ]
    }
    # More document types can be added here
}

# --- END: Define Quality Assessment Criteria --- #

def process_uploaded_document(pdf_file_stream, original_filename: str, selected_document_type: str = None):
    """
    Processes an uploaded PDF: extracts text, (optionally) determines document type, 
    and initiates quality assessment.
    Returns an assessment_id.
    """
    global _next_assessment_id
    assessment_id = str(_next_assessment_id)
    _next_assessment_id += 1

    saved_pdf_filename = None
    saved_pdf_full_path = None

    # 0. Save the PDF to a file first
    # The pdf_file_stream needs to be readable multiple times or saved.
    # Assuming pdf_file_stream is a SpooledTemporaryFile or similar that can be read.
    # It's better to save it to a permanent location if we need to access it later for preview.
    try:
        # Ensure the stream is at the beginning if it has been read before (might not be necessary depending on stream type)
        # pdf_file_stream.seek(0) # This might be needed if stream was already processed by something else
        
        # Sanitize original_filename before using it in a path
        secure_original_filename = secure_filename(original_filename)
        # Create a unique filename using assessment_id to prevent overwrites and ensure association
        saved_pdf_filename = f"{assessment_id}_{secure_original_filename}"
        saved_pdf_full_path = os.path.join(QA_PDF_UPLOAD_DIR, saved_pdf_filename)
        
        with open(saved_pdf_full_path, 'wb') as f_out:
            # Read from the input stream and write to the file stream
            # pdf_file_stream might be a SpooledTemporaryFile from Flask/Werkzeug
            # or a BytesIO if constructed manually for testing.
            # Ensure pdf_file_stream is at the beginning if it's to be re-read for text extraction
            pdf_file_stream.seek(0) # IMPORTANT: Reset stream before reading for saving
            f_out.write(pdf_file_stream.read())
        
        print(f"PDF for assessment {assessment_id} saved to: {saved_pdf_full_path}")
        # IMPORTANT: After reading the stream to save it, reset it again if extract_text_from_pdf needs to read it from the start
        pdf_file_stream.seek(0)

    except Exception as e_save:
        print(f"Error saving PDF for assessment {assessment_id}: {e_save}")
        # Decide if this is a critical error. For now, we'll proceed with text extraction if possible,
        # but preview might not work.
        # saved_pdf_filename will remain None

    # 1. Extract text from PDF (using the existing utility)
    try:
        # Assuming your extract_text_from_pdf can take a stream directly.
        # You might need to adjust ocr_language if it's configurable by user.
        text_content = extract_text_from_pdf(pdf_file_stream, ocr_language='eng') 
    except Exception as e:
        # Log the exception e
        print(f"Error extracting text for {assessment_id}: {e}")
        _assessments_db[assessment_id] = {
            "status": "error", 
            "message": f"Text extraction failed: {e}", 
            "filename": original_filename,
            "progress": {}
        }
        return assessment_id

    if not text_content:
        _assessments_db[assessment_id] = {
            "status": "error", 
            "message": "PDF text empty.", 
            "filename": original_filename,
            "progress": {}
        }
        return assessment_id
    # text_content = "Dummy text content for now." # Remove dummy content

    # 2. Determine document type
    document_type_to_store = selected_document_type
    classification_evidence = None
    
    # If document type wasn't specified, use AI classifier to determine it
    if not document_type_to_store or document_type_to_store == "":
        try:
            # Attempt to classify the document
            detected_type, type_scores = classify_document_type(text_content)
            
            if detected_type and detected_type != "Unknown" and detected_type != "Uncertain":
                document_type_to_store = detected_type
                classification_evidence = get_document_evidence(text_content, detected_type)
                print(f"Document automatically classified as: {document_type_to_store}")
            else:
                document_type_to_store = "Unknown"
                print(f"Document could not be automatically classified. Scores: {type_scores}")
        except Exception as classify_error:
            print(f"Error during document classification: {classify_error}")
            document_type_to_store = "Unknown"
    
    if document_type_to_store not in QUALITY_ASSESSMENT_TOOLS:
        print(f"Document type '{document_type_to_store}' not supported for quality assessment.")
        document_type_to_store = "Unknown"

    # --- Fetch LLM Config IN REQUEST CONTEXT (before submitting to thread) ---
    llm_config_for_task = None
    try:
        current_llm_main_config = get_current_llm_config(session) # This uses flask.session
        provider_name = current_llm_main_config['provider_name']
        api_key_val = get_api_key_for_provider(provider_name, session) # This uses flask.session
        if not api_key_val:
            raise ValueError(f"API Key for {provider_name} not found in session or environment.")
        
        llm_config_for_task = {
            "provider_name": provider_name,
            "model_id": current_llm_main_config['model_id'],
            "base_url": get_base_url_for_provider(provider_name), # Assuming this doesn't need session
            "api_key": api_key_val
        }
        print(f"LLM config fetched for task {assessment_id}: Provider {provider_name}")
    except Exception as e_conf_fetch:
        print(f"Error fetching LLM config in request context for {assessment_id}: {e_conf_fetch}")
        _assessments_db[assessment_id] = {
            "status": "error", 
            "filename": original_filename,
            "document_type": document_type_to_store,
            "message": f"Failed to prepare LLM config: {e_conf_fetch}",
            "progress": {"message": "LLM config fetch error"}
        }
        return assessment_id
    # --- End Fetch LLM Config ---

    # 3. (Placeholder) Initiate quality assessment based on document type
    # For now, just store info. Later, this would trigger async assessment.
    _assessments_db[assessment_id] = {
        "status": "pending_assessment", 
        "filename": original_filename,
        "document_type": document_type_to_store,
        "text_preview": text_content[:500] + ("..." if len(text_content) > 500 else ""),
        "raw_text": text_content,
        "assessment_details": None,
        "user_review": None,
        "classification_evidence": classification_evidence,  # Store classification evidence if available
        "saved_pdf_filename": saved_pdf_filename, # Store the filename (not full path for security in client)
        "progress": {"current": 0, "total": 0, "message": "Assessment queued"} # Initial progress
    }
    print(f"Document {original_filename} processed. Assessment ID: {assessment_id}. Type: {document_type_to_store}. Queuing AI assessment.")
    
    # Save assessments to file after adding new one
    _save_assessments_to_file(assessment_id_to_log=assessment_id)
    
    # Submit run_ai_quality_assessment to the executor
    try:
        # Make sure current_app is available here. If services.py is part of the app context, it should be.
        # Otherwise, the executor needs to be passed in or accessed differently.
        current_app.executor.submit(run_ai_quality_assessment, assessment_id, current_app._get_current_object(), llm_config_for_task)
        print(f"AI assessment task for {assessment_id} submitted to executor.")
    except Exception as e_submit:
        print(f"Error submitting task for {assessment_id}: {e_submit}")
        _assessments_db[assessment_id]["status"] = "error"
        _assessments_db[assessment_id]["message"] = f"Failed to start task: {e_submit}"
        _assessments_db[assessment_id]["progress"]["message"] = "Error starting task"

    return assessment_id

def get_assessment_result(assessment_id: str):
    """Retrieves the assessment result for a given ID."""
    data = _assessments_db.get(assessment_id)
    if data:
        details = data.get('assessment_details')
        details_count = len(details) if isinstance(details, list) else 0 # Safe way to get length
        print(f"GET_RESULT_LOGIC: For assessment ID {assessment_id}, status: {data.get('status')}, details count being returned: {details_count}, summary: {data.get('summary_negative_findings')}")
    else:
        print(f"GET_RESULT_LOGIC: No data found in _assessments_db for assessment ID {assessment_id}")
    return data

# --- Functions to be developed further --- #

def get_quality_criteria_for_type(document_type: str):
    """Returns the quality assessment tool and criteria items for a given document type."""
    if not document_type or document_type == "Unknown":
        # Potentially return a generic checklist or None
        return None 
    return QUALITY_ASSESSMENT_TOOLS.get(document_type)

MAX_TEXT_SEGMENT_FOR_LLM = 30000 # Max characters to send to LLM per criterion (adjust as needed)

def _construct_quality_assessment_prompt(criterion_text: str, criterion_guidance: Optional[str], document_text_segment: str, document_type: str = "Cohort Study") -> Dict:
    """
    Construct a prompt for quality assessment based on document type and criterion.
    
    Args:
        criterion_text: The text of the criterion to assess
        criterion_guidance: Optional guidance for the criterion
        document_text_segment: The document text to evaluate
        document_type: The type of the document (default: "Cohort Study")
        
    Returns:
        Dict with system_prompt and main_prompt
    """
    # Use the appropriate prompt template for this document type
    return get_assessment_prompt(
        document_type=document_type,
        criterion_text=criterion_text,
        criterion_guidance=criterion_guidance,
        document_text=document_text_segment
    )

def _parse_llm_json_response(llm_response_raw: str) -> Optional[Dict]:
    if not llm_response_raw or not isinstance(llm_response_raw, str):
        return None
    try:
        json_block_match = re.search(r'```json\s*(\{.*?\})\s*```', llm_response_raw, re.DOTALL)
        if json_block_match:
            json_str_to_parse = json_block_match.group(1)
            return json.loads(json_str_to_parse)
        first_brace = llm_response_raw.find('{')
        last_brace = llm_response_raw.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            potential_json_str = llm_response_raw[first_brace : last_brace + 1]
            return json.loads(potential_json_str)
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON from LLM output: {e}. Raw: {llm_response_raw[:200]}")
        return None
    except Exception as e_parse:
        print(f"Unexpected error parsing LLM output: {e_parse}. Raw: {llm_response_raw[:200]}")
        return None

def run_ai_quality_assessment(assessment_id: str, app_context=None, llm_config=None):
    if not llm_config or not llm_config.get("api_key"):
        print(f"Error for {assessment_id}: LLM config missing for background task.")
        if assessment_id in _assessments_db:
            _assessments_db[assessment_id]["status"] = "error"
            _assessments_db[assessment_id]["message"] = "LLM config not provided to worker."
            if "progress" in _assessments_db[assessment_id]: _assessments_db[assessment_id]["progress"]["message"] = "Internal config error."
        return

    if app_context:
        with app_context.app_context():
            _execute_assessment_logic(assessment_id, llm_config)
    else:
        print(f"Warning for {assessment_id}: Running AI assessment without explicit app context.")
        _execute_assessment_logic(assessment_id, llm_config)

def _execute_assessment_logic(assessment_id: str, llm_config: Dict):
    try:
        assessment_data = _assessments_db.get(assessment_id)
        import time
        time.sleep(0.1) 

        if not assessment_data:
            print(f"Assessment data for {assessment_id} not found in _execute_assessment_logic.")
            return
        
        # Ensure assessment_details is a list, not None, before processing
        if assessment_data.get('assessment_details') is None:
            assessment_data['assessment_details'] = []
            print(f"EXECUTE_LOGIC: Initialized assessment_details to [] for {assessment_id} as it was None.")

        if assessment_data.get('status') in ['completed', 'error']:
            print(f"Assessment {assessment_id} already processed ({assessment_data.get('status')}). Skipping.")
            return
        
        print(f"Background task started for {assessment_id} with provider {llm_config.get('provider_name')}")
        assessment_data['status'] = 'processing_assessment'
        assessment_data['progress'] = {"current": 0, "total": 0, "message": "Initializing assessment..."}

        provider_name = llm_config['provider_name']
        model_id = llm_config['model_id']
        base_url = llm_config['base_url']
        api_key = llm_config['api_key']

        text_content = assessment_data['raw_text']
        document_type = assessment_data['document_type']
        criteria_tool_info = get_quality_criteria_for_type(document_type)

        if not criteria_tool_info:
            assessment_data['status'] = 'error'
            assessment_data['message'] = f"No tool for type: {document_type}"
            assessment_data['progress']["message"] = "Tool definition error"
            return

        criteria_list = criteria_tool_info.get("criteria", [])
        total_criteria = len(criteria_list)
        assessment_data['progress']['total'] = total_criteria
        assessment_data['progress']['message'] = f"Starting assessment of {total_criteria} criteria..."
        detailed_results = []
        document_text_segment = text_content[:MAX_TEXT_SEGMENT_FOR_LLM]

        for i, criterion in enumerate(criteria_list):
            current_progress = i + 1
            progress_msg = f"Assessing criterion {current_progress}/{total_criteria}: {criterion['text'][:30]}..."
            assessment_data['progress']['current'] = current_progress
            assessment_data['progress']['message'] = progress_msg
            print(f"  Thread for {assessment_id}: {progress_msg}")
            
            prompt_construct = _construct_quality_assessment_prompt(
                criterion_text=criterion['text'],
                criterion_guidance=criterion.get('guidance'),
                document_text_segment=document_text_segment,
                document_type=document_type
            )
            
            print(f"  Thread for {assessment_id}: Using assessment template for {document_type}")
            
            try:
                llm_response_raw = call_llm_api_raw_content(
                    prompt_construct, provider_name, model_id, api_key, base_url, max_tokens_override=600 # Increased max_tokens for potentially longer JSON
                )
                parsed_assessment = _parse_llm_json_response(llm_response_raw)
                if parsed_assessment and isinstance(parsed_assessment, dict):
                    detailed_results.append({
                        "criterion_id": criterion['id'], "criterion_text": criterion['text'],
                        "judgment": parsed_assessment.get("judgment", "Error: Missing judgment"),
                        "reason": parsed_assessment.get("reason", "Error: Missing reason"),
                        "evidence_quotes": parsed_assessment.get("evidence_quotes", [])
                    })
                else:
                    detailed_results.append({"criterion_id": criterion['id'], "criterion_text": criterion['text'], "judgment": "Error: Parse Failure", "reason": f"Raw: {llm_response_raw[:100] if llm_response_raw else 'None'}...", "evidence_quotes": []})
            except Exception as e_llm_call:
                detailed_results.append({"criterion_id": criterion['id'], "criterion_text": criterion['text'], "judgment": "Error: API Call Failed", "reason": str(e_llm_call), "evidence_quotes": []})

        assessment_data['assessment_details'] = detailed_results
        assessment_data['status'] = 'completed'
        assessment_data['progress']['message'] = "Assessment completed!"
        assessment_data['progress']['current'] = total_criteria

        # Calculate a simple summary: count of negative judgments
        negative_judgment_count = 0
        if detailed_results:
            for res_item in detailed_results:
                judgment = res_item.get("judgment", "").lower()
                # Define what constitutes a negative judgment based on your LLM's typical output
                if "no" in judgment or "high risk" in judgment or "poor" in judgment or judgment == "not met":
                    negative_judgment_count += 1
        assessment_data['summary_negative_findings'] = negative_judgment_count
        assessment_data['summary_total_criteria_evaluated'] = total_criteria
        
        # Force update to ensure the assessment is marked as completed
        if assessment_id in _assessments_db:
            _assessments_db[assessment_id] = assessment_data
            print(f"EXECUTE_LOGIC: Assessment {assessment_id} details count IN DB before save: {len(_assessments_db[assessment_id].get('assessment_details', []))}")
            print(f"EXECUTE_LOGIC: Status IN DB before save: {_assessments_db[assessment_id].get('status')}")
            print(f"EXECUTE_LOGIC: Summary negative findings IN DB: {_assessments_db[assessment_id].get('summary_negative_findings')}") # Log new summary

        # Save completed assessments to file
        _save_assessments_to_file(assessment_id_to_log=assessment_id)
        
        print(f"Background task for {assessment_id} finished. Results: {len(detailed_results)}")
        
        # Add more debugging info
        if detailed_results:
            print(f"First result item: {detailed_results[0]['criterion_id']} - {detailed_results[0]['judgment']}")
            print(f"Assessment completed for type: {document_type}. Setting status to completed.")
            # Print the complete assessment data structure to verify it's properly saved
            print(f"Assessment data keys: {assessment_data.keys()}")
            print(f"Assessment status: {assessment_data['status']}")
            print(f"Results count in assessment: {len(assessment_data['assessment_details'])}")
        else:
            print(f"Warning: No detailed results were generated for {assessment_id}.")

    except Exception as e_outer:
        print(f"CRITICAL ERROR in _execute_assessment_logic for {assessment_id}: {e_outer}")
        traceback.print_exc()
        if assessment_id in _assessments_db and _assessments_db[assessment_id] is not None:
            _assessments_db[assessment_id]['status'] = 'error'
            _assessments_db[assessment_id]['message'] = f"Critical background task error: {str(e_outer)[:100]}" # Keep error message concise
            if 'progress' in _assessments_db[assessment_id] and _assessments_db[assessment_id]['progress'] is not None:
                 _assessments_db[assessment_id]['progress']['message'] = "Critical error during processing"
                 
            # Save error state to file
            _save_assessments_to_file(assessment_id_to_log=assessment_id) # Pass ID for logging within save


# Example of how you might call the assessment after processing:
# if assessment_id and _assessments_db[assessment_id]['status'] == 'pending':
#     run_ai_quality_assessment(assessment_id) 