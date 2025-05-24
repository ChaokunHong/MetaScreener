# This file will contain the core business logic for the quality assessment feature.

# We will need to import PDF extraction utilities, LLM interaction functions, etc.
from app.utils.utils import extract_text_from_pdf
# from llm_integrations import classify_document_type_llm, assess_quality_llm 
# (assuming llm_integrations is a module we might create or use existing from main app)

from config.config import get_current_llm_config, get_llm_providers_info, get_base_url_for_provider, get_api_key_for_provider
from app.utils.utils import call_llm_api_raw_content # Using raw content to get JSON
from werkzeug.utils import secure_filename # Added for saving PDF

from flask import session, current_app # <--- IMPORT current_app
import json
import re
from typing import Dict, Optional
import traceback # Added for more detailed error logging in background tasks
from app.quality_assessment_module.models import classify_document_type, get_document_evidence
from app.quality_assessment_module.prompts import get_assessment_prompt # Import the prompt generator
import os
import pickle
from pathlib import Path
import time
from gevent import spawn, joinall # Ensure gevent is imported here
import threading
import fcntl  # For file locking on Unix systems
import uuid
import redis # Add this

# Placeholder for storing assessment data (in a real app, this would be a database)
_assessments_db = {}
_next_assessment_id = 1
_id_lock = threading.Lock()  # Thread lock for ID generation

# Define file path for persistent storage
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
ASSESSMENTS_FILE = os.path.join(DATA_DIR, 'assessments.pickle')
ID_LOCK_FILE = os.path.join(DATA_DIR, 'id_generation.lock')  # File lock for ID generation
# Define directory for storing uploaded PDFs for quality assessment preview
QA_PDF_UPLOAD_DIR = os.path.join(DATA_DIR, 'quality_assessment_pdfs')

# Define cleanup interval (1 hour in seconds)
QA_PDF_CLEANUP_INTERVAL_SECONDS = 60 * 60 

# Create data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)
# Create QA PDF upload directory if it doesn't exist
os.makedirs(QA_PDF_UPLOAD_DIR, exist_ok=True)

# New Redis client instance specifically for Celery results, mirrors Celery task's client
# This avoids issues with decode_responses=True from redis_storage.py's client
# if Celery stores pickled bytes.
_celery_redis_client = None

def get_celery_redis_client():
    global _celery_redis_client
    if _celery_redis_client is None:
        # Use the same Redis database as Celery broker (db=1)
        redis_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
        # IMPORTANT: Celery task uses pickle, so we should not decode responses automatically here.
        _celery_redis_client = redis.Redis.from_url(redis_url)
    return _celery_redis_client

# Redis client for assessment data storage
_assessment_redis_client = None

def get_assessment_redis_client():
    global _assessment_redis_client
    if _assessment_redis_client is None:
        # Use the same Redis database as Celery broker (db=1) for consistency
        redis_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
        _assessment_redis_client = redis.Redis.from_url(redis_url, decode_responses=False)
        print(f"REDIS_CONFIG: Assessment Redis client using {redis_url}")
    return _assessment_redis_client

def _save_assessment_to_redis(assessment_id: str, assessment_data: dict):
    """Save assessment data to Redis for multi-process sharing"""
    try:
        redis_client = get_assessment_redis_client()
        serialized_data = pickle.dumps(assessment_data)
        redis_client.setex(f"qa_assessment:{assessment_id}", 86400, serialized_data)  # 24 hours TTL
        print(f"REDIS_SAVE: Saved assessment {assessment_id} to Redis")
    except Exception as e:
        print(f"REDIS_SAVE_ERROR: Failed to save assessment {assessment_id} to Redis: {e}")

def _get_assessment_from_redis(assessment_id: str) -> dict:
    """Get assessment data from Redis"""
    try:
        redis_client = get_assessment_redis_client()
        serialized_data = redis_client.get(f"qa_assessment:{assessment_id}")
        if serialized_data:
            assessment_data = pickle.loads(serialized_data)
            print(f"REDIS_GET: Retrieved assessment {assessment_id} from Redis")
            return assessment_data
    except Exception as e:
        print(f"REDIS_GET_ERROR: Failed to get assessment {assessment_id} from Redis: {e}")
    return None

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
            current_assessment_data_to_save = _assessments_db.get(assessment_id_to_log) # Use .get() for safety
            if current_assessment_data_to_save: # Check if data exists
                assessment_details = current_assessment_data_to_save.get('assessment_details', [])
                details_count = len(assessment_details) if assessment_details is not None else 0 # Safe count
                
                print(f"SAVE_LOGIC: For {assessment_id_to_log}, "
                      f"status being saved: {current_assessment_data_to_save.get('status')}, "
                      f"details count: {details_count}, " # Use safe count
                      f"summary: {current_assessment_data_to_save.get('summary_negative_findings')}")
            else:
                print(f"SAVE_LOGIC: Attempted to log save for {assessment_id_to_log}, but data not found in _assessments_db.")
        
        with open(ASSESSMENTS_FILE, 'wb') as f:
            pickle.dump((_assessments_db, _next_assessment_id), f)
        print(f"SAVE_LOGIC: Full _assessments_db (count: {len(_assessments_db)}) and _next_assessment_id ({_next_assessment_id}) saved to {ASSESSMENTS_FILE}")

    except Exception as e:
        print(f"Error saving assessment data: {e}")
        traceback.print_exc() # Print full traceback for saving errors

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

def _generate_safe_assessment_id():
    """
    Generate assessment ID safely with file locking to prevent concurrent access issues.
    Uses both thread lock and file lock for maximum safety across processes.
    """
    global _next_assessment_id
    
    # Use thread lock for thread safety within same process
    with _id_lock:
        # Use file lock for process safety across different workers
        try:
            # Create/open lock file
            with open(ID_LOCK_FILE, 'w') as lock_file:
                # Acquire exclusive file lock (Unix systems)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                
                try:
                    # Reload current state from file to get latest ID
                    _load_assessments_from_file()
                    
                    # Generate new ID
                    new_id = str(_next_assessment_id)
                    _next_assessment_id += 1
                    
                    # Save updated state immediately
                    _save_assessments_to_file()
                    
                    print(f"SAFE_ID_GEN: Generated assessment ID {new_id} (next will be {_next_assessment_id})")
                    return new_id
                    
                finally:
                    # Release file lock automatically when exiting with statement
                    pass
                    
        except Exception as e:
            print(f"ERROR in safe ID generation: {e}")
            # Fallback to UUID if file locking fails
            fallback_id = str(uuid.uuid4())
            print(f"SAFE_ID_GEN: Using fallback UUID: {fallback_id}")
            return fallback_id

# --- START: Define Quality Assessment Criteria --- #

# Define known quality assessment tools and their items
# This contains complete, standardized quality assessment tools
# for different document types, following international standards.
QUALITY_ASSESSMENT_TOOLS = {
    "Systematic Review": {
        "tool_name": "AMSTAR 2 (A MeaSurement Tool to Assess systematic Reviews) - 16 items",
        "criteria": [
            {"id": "sr_q1", "text": "Did the research questions and inclusion criteria for the review include the components of PICO?", "guidance": "PICO: Population, Intervention, Comparator, Outcome. The research question should be clearly defined and include all relevant PICO components.", "critical": True},
            {"id": "sr_q2", "text": "Did the report of the review contain an explicit statement that the review methods were established prior to the conduct of the review and did the report justify any significant deviations from the protocol?", "guidance": "Look for mention of a protocol (e.g., PROSPERO registration, published protocol). Any deviations from the protocol should be justified.", "critical": True},
            {"id": "sr_q3", "text": "Did the review authors explain their selection of the study designs for inclusion in the review?", "guidance": "Consider if reasons are given for why certain study designs were included or excluded. The rationale should be appropriate for the research question."},
            {"id": "sr_q4", "text": "Did the review authors use a comprehensive literature search strategy?", "guidance": "At least two databases should be searched. The search should include keywords and/or MeSH terms, reference list searching, and other comprehensive strategies.", "critical": True},
            {"id": "sr_q5", "text": "Did the review authors perform study selection in duplicate?", "guidance": "Look for mention of two independent reviewers for study selection with a process for resolving disagreements."},
            {"id": "sr_q6", "text": "Did the review authors perform data extraction in duplicate?", "guidance": "Data extraction should be performed by at least two independent reviewers with a process for resolving disagreements."},
            {"id": "sr_q7", "text": "Did the review authors provide a list of excluded studies and justify the exclusions?", "guidance": "A list of excluded studies (at full-text level) should be provided with reasons for exclusion.", "critical": True},
            {"id": "sr_q8", "text": "Did the review authors describe the included studies in adequate detail?", "guidance": "Adequate details should include: study design, population, interventions, comparators, outcomes, and study characteristics."},
            {"id": "sr_q9", "text": "Did the review authors use a satisfactory technique for assessing the risk of bias (RoB) in individual studies that were included in the review?", "guidance": "An appropriate tool should be used for assessing risk of bias (e.g., RoB 2 for RCTs, ROBINS-I for non-randomized studies).", "critical": True},
            {"id": "sr_q10", "text": "Did the review authors report on the sources of funding for the studies included in the review?", "guidance": "Information about funding sources for included studies should be reported."},
            {"id": "sr_q11", "text": "If meta-analysis was performed, did the review authors use appropriate methods for statistical combination of results?", "guidance": "Appropriate statistical methods should be used. Fixed vs. random effects model choice should be justified.", "critical": True},
            {"id": "sr_q12", "text": "If meta-analysis was performed, did the review authors assess the potential impact of RoB in individual studies on the results of the meta-analysis or other evidence synthesis?", "guidance": "The impact of risk of bias on the results should be assessed and discussed.", "critical": True},
            {"id": "sr_q13", "text": "Did the review authors account for RoB in individual studies when interpreting/discussing the results of the review?", "guidance": "Risk of bias should be considered in the interpretation and discussion of results."},
            {"id": "sr_q14", "text": "Did the review authors provide a satisfactory explanation for, and discussion of, any heterogeneity observed in the results of the review?", "guidance": "Heterogeneity should be investigated and explained. Sources of heterogeneity should be explored."},
            {"id": "sr_q15", "text": "If they performed quantitative synthesis, did the review authors carry out an adequate investigation of publication bias (small study bias) and discuss its likely impact on the results of the review?", "guidance": "Publication bias should be investigated using appropriate methods (e.g., funnel plots, statistical tests) when there are sufficient studies."},
            {"id": "sr_q16", "text": "Did the review authors report any potential sources of conflict of interest, including any funding they received for conducting the review?", "guidance": "Sources of funding and potential conflicts of interest for the review should be clearly reported."}
        ]
    },
    "RCT": {
        "tool_name": "Cochrane RoB 2 (Risk of Bias tool for randomized trials) - Complete",
        "criteria": [
            # Domain 1: Randomization process
            {"id": "rct_d1_1", "text": "Was the allocation sequence random?", "domain": "D1: Randomization process", "guidance": "Consider if the allocation sequence was adequately generated (e.g., computer-generated random numbers, random number tables)."},
            {"id": "rct_d1_2", "text": "Was the allocation sequence concealed until participants were enrolled and assigned to interventions?", "domain": "D1: Randomization process", "guidance": "Assess if allocation was concealed from those recruiting/enrolling participants (e.g., central allocation, sequentially numbered sealed envelopes)."},
            {"id": "rct_d1_3", "text": "Were there baseline imbalances that suggest a problem with randomization?", "domain": "D1: Randomization process", "guidance": "Look for imbalances in baseline characteristics that might indicate randomization failure."},
            
            # Domain 2: Deviations from intended interventions
            {"id": "rct_d2_1", "text": "Were participants aware of their assigned intervention during the trial?", "domain": "D2: Deviations from intended interventions", "guidance": "Assess if participants were blinded to treatment allocation."},
            {"id": "rct_d2_2", "text": "Were carers and people delivering the interventions aware of participants' assigned intervention during the trial?", "domain": "D2: Deviations from intended interventions", "guidance": "Assess if care providers/personnel were blinded to treatment allocation."},
            {"id": "rct_d2_3", "text": "Were there deviations from the intended intervention that arose because of the experimental context?", "domain": "D2: Deviations from intended interventions", "guidance": "Consider deviations that would not occur outside the trial context."},
            {"id": "rct_d2_4", "text": "Was an appropriate analysis used to estimate the effect of assignment to intervention?", "domain": "D2: Deviations from intended interventions", "guidance": "For effect of assignment to intervention: intention-to-treat analysis should be used."},
            
            # Domain 3: Missing outcome data
            {"id": "rct_d3_1", "text": "Were data for this outcome available for all, or nearly all, participants randomized?", "domain": "D3: Missing outcome data", "guidance": "Assess completeness of outcome data and whether missing data rates are similar across groups."},
            {"id": "rct_d3_2", "text": "Is there evidence that the result was not biased by missing outcome data?", "domain": "D3: Missing outcome data", "guidance": "Consider if missing data could substantially impact the observed effect."},
            {"id": "rct_d3_3", "text": "Could missingness in the outcome depend on its true value?", "domain": "D3: Missing outcome data", "guidance": "Assess if reasons for missing data are related to the outcome itself."},
            
            # Domain 4: Measurement of the outcome
            {"id": "rct_d4_1", "text": "Was the method of measuring the outcome inappropriate?", "domain": "D4: Measurement of the outcome", "guidance": "Consider if the measurement method was valid and reliable."},
            {"id": "rct_d4_2", "text": "Could measurement or ascertainment of the outcome have differed between intervention groups?", "domain": "D4: Measurement of the outcome", "guidance": "Assess if outcome assessment methods differed between groups."},
            {"id": "rct_d4_3", "text": "Were outcome assessors aware of the intervention received by study participants?", "domain": "D4: Measurement of the outcome", "guidance": "Consider if outcome assessors were blinded to treatment allocation."},
            {"id": "rct_d4_4", "text": "Could assessment of the outcome have been influenced by knowledge of intervention received?", "domain": "D4: Measurement of the outcome", "guidance": "For subjective outcomes, knowledge of intervention could bias assessment."},
            
            # Domain 5: Selection of the reported result
            {"id": "rct_d5_1", "text": "Were the data that produced this result analyzed in accordance with a pre-specified analysis plan?", "domain": "D5: Selection of the reported result", "guidance": "Consider if the analysis matches the planned approach in the protocol."},
            {"id": "rct_d5_2", "text": "Is the numerical result being assessed likely to have been selected, on the basis of the results, from multiple eligible outcome measurements?", "domain": "D5: Selection of the reported result", "guidance": "Assess selective reporting of outcome measurements or time points."},
            {"id": "rct_d5_3", "text": "Is the numerical result being assessed likely to have been selected, on the basis of the results, from multiple eligible analyses of the data?", "domain": "D5: Selection of the reported result", "guidance": "Consider selective reporting of analyses (e.g., subgroup analyses, adjusted vs unadjusted)."}
        ]
    },
    "Diagnostic Study": {
        "tool_name": "QUADAS-2 (Quality Assessment of Diagnostic Accuracy Studies) - Complete",
        "criteria": [
            # Domain 1: Patient Selection - Risk of Bias
            {"id": "ds_d1_rb1", "text": "Was a consecutive or random sample of patients enrolled?", "domain": "D1: Patient Selection - Risk of Bias", "guidance": "Consecutive or random sampling reduces selection bias. Case-control designs or convenience sampling may introduce bias."},
            {"id": "ds_d1_rb2", "text": "Was a case-control design avoided?", "domain": "D1: Patient Selection - Risk of Bias", "guidance": "Case-control designs can overestimate diagnostic accuracy."},
            {"id": "ds_d1_rb3", "text": "Did the study avoid inappropriate exclusions?", "domain": "D1: Patient Selection - Risk of Bias", "guidance": "Exclusions should be clearly described and appropriate for the research question."},
            
            # Domain 1: Patient Selection - Applicability
            {"id": "ds_d1_ac1", "text": "Are there concerns that the included patients and setting do not match the review question?", "domain": "D1: Patient Selection - Applicability", "guidance": "Consider if patient characteristics, setting, and intended use of index test match the review question."},
            
            # Domain 2: Index Test - Risk of Bias
            {"id": "ds_d2_rb1", "text": "Were the index test results interpreted without knowledge of the results of the reference standard?", "domain": "D2: Index Test - Risk of Bias", "guidance": "Interpretation should be blinded to reference standard results to avoid bias."},
            {"id": "ds_d2_rb2", "text": "If a threshold was used, was it pre-specified?", "domain": "D2: Index Test - Risk of Bias", "guidance": "Pre-specified thresholds prevent data-driven threshold selection which can inflate accuracy."},
            
            # Domain 2: Index Test - Applicability
            {"id": "ds_d2_ac1", "text": "Are there concerns that the index test, its conduct, or interpretation differ from the review question?", "domain": "D2: Index Test - Applicability", "guidance": "Consider if the index test was performed as it would be in practice."},
            
            # Domain 3: Reference Standard - Risk of Bias
            {"id": "ds_d3_rb1", "text": "Is the reference standard likely to correctly classify the target condition?", "domain": "D3: Reference Standard - Risk of Bias", "guidance": "The reference standard should be the best available method for establishing presence/absence of target condition."},
            {"id": "ds_d3_rb2", "text": "Were the reference standard results interpreted without knowledge of the results of the index test?", "domain": "D3: Reference Standard - Risk of Bias", "guidance": "Interpretation should be blinded to index test results to avoid bias."},
            
            # Domain 3: Reference Standard - Applicability
            {"id": "ds_d3_ac1", "text": "Are there concerns that the target condition as defined by the reference standard does not match the question?", "domain": "D3: Reference Standard - Applicability", "guidance": "Consider if the reference standard defines the same target condition as in the review question."},
            
            # Domain 4: Flow and Timing - Risk of Bias
            {"id": "ds_d4_rb1", "text": "Was there an appropriate interval between index test and reference standard?", "domain": "D4: Flow and Timing - Risk of Bias", "guidance": "The interval should be short enough that the target condition is unlikely to change."},
            {"id": "ds_d4_rb2", "text": "Did all patients receive the same reference standard?", "domain": "D4: Flow and Timing - Risk of Bias", "guidance": "Differential verification can introduce bias."},
            {"id": "ds_d4_rb3", "text": "Were all patients included in the analysis?", "domain": "D4: Flow and Timing - Risk of Bias", "guidance": "Withdrawals should be explained and unlikely to introduce bias."}
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
    # Use safe ID generation to prevent concurrent access issues
    assessment_id = _generate_safe_assessment_id()

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
        _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
        return assessment_id

    if not text_content:
        _assessments_db[assessment_id] = {
            "status": "error", 
            "message": "PDF text empty.", 
            "filename": original_filename,
            "progress": {}
        }
        _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
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
        _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
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
    
    # Save assessments to Redis and file after adding new one
    _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
    _save_assessments_to_file(assessment_id_to_log=assessment_id)
    
    # Submit run_ai_quality_assessment to the executor
    try:
        # Make sure current_app is available here. If services.py is part of the app context, it should be.
        # Otherwise, the executor needs to be passed in or accessed differently.
        spawn(run_ai_quality_assessment, assessment_id, current_app._get_current_object(), llm_config_for_task)
        print(f"AI assessment task for {assessment_id} submitted to gevent spawn.")
    except Exception as e_submit:
        print(f"Error submitting task for {assessment_id} via gevent.spawn: {e_submit}")
        _assessments_db[assessment_id]["status"] = "error"
        _assessments_db[assessment_id]["message"] = f"Failed to start task: {e_submit}"
        _assessments_db[assessment_id]["progress"]["message"] = "Error starting task"
        _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])

    return assessment_id

def register_celery_item(filename: str, document_type: str, celery_processing_uuid: str) -> str:
    """
    Registers an individual item that will be processed by a Celery batch task.
    Generates a numerical ID, creates an initial entry in _assessments_db.
    Returns the numerical_id.
    """
    numerical_id = _generate_safe_assessment_id() # This handles its own load/save for ID generation
    
    # Create initial entry in _assessments_db
    _assessments_db[numerical_id] = {
        "status": "pending_celery", # New status indicating it's waiting for Celery
        "filename": filename,
        "document_type": document_type,
        "celery_processing_uuid": celery_processing_uuid, # Link to the main Celery task result
        "progress": {"current": 0, "total": 100, "message": "Queued for Celery processing"},
        "assessment_details": [], # Initialize
        "raw_text": "Text will be processed by Celery.", # Placeholder
        "text_preview": "N/A",
        "user_review": None,
        "classification_evidence": None,
        "saved_pdf_filename": None # Celery path handles files differently for preview
    }
    _save_assessment_to_redis(numerical_id, _assessments_db[numerical_id])
    _save_assessments_to_file(assessment_id_to_log=numerical_id) # Save this new entry
    print(f"SERVICE_LOGIC: Registered celery item. Numerical ID: {numerical_id}, Filename: {filename}, Celery UUID: {celery_processing_uuid}")
    return numerical_id

def get_assessment_result(assessment_id: str):
    """
    Retrieves the assessment result for a given numerical ID.
    If the item is pending Celery processing, it attempts to fetch and update 
    its status from the main Celery batch result in Redis.
    Now with Redis support for multi-process environments.
    """
    # Ensure assessment_id is treated as a string key for the dictionary
    str_assessment_id = str(assessment_id)
    
    # First, try to get from Redis (for multi-process environments)
    item_data = _get_assessment_from_redis(str_assessment_id)
    
    # If not in Redis, check legacy in-memory storage
    if item_data is None:
        item_data = _assessments_db.get(str_assessment_id)
        # If found in memory, also save to Redis for future access
        if item_data is not None:
            _save_assessment_to_redis(str_assessment_id, item_data)

    if item_data is None:
        print(f"GET_RESULT_LOGIC: No data found in Redis or _assessments_db for numerical ID {str_assessment_id}")
        return None

    if item_data.get("status") == "pending_celery":
        print(f"GET_RESULT_LOGIC: Item {str_assessment_id} is 'pending_celery'. Checking Celery batch results.")
        celery_processing_uuid = item_data.get("celery_processing_uuid")
        
        if not celery_processing_uuid:
            print(f"GET_RESULT_LOGIC: ERROR - Item {str_assessment_id} is 'pending_celery' but missing 'celery_processing_uuid'.")
            item_data["status"] = "error"
            item_data["message"] = "Configuration error: Missing Celery processing UUID link."
            return item_data

        try:
            r_client = get_celery_redis_client()
            redis_key_celery_batch = f"quality_results:{celery_processing_uuid}"
            celery_batch_raw = r_client.get(redis_key_celery_batch)

            if celery_batch_raw:
                print(f"GET_RESULT_LOGIC: Found Celery batch raw data in Redis for Celery UUID {celery_processing_uuid} (linked to item {str_assessment_id}).")
                celery_batch_data = pickle.loads(celery_batch_raw)
                
                item_filename = item_data.get("filename")
                file_specific_result = None
                
                for res in celery_batch_data.get("results", []):
                    if isinstance(res, dict) and res.get("filename") == item_filename: # Match on original_filename if Celery task uses it
                        # Fallback: if Celery task uses 'original_filename' in its results items
                        if res.get("filename") is None and 'original_filename' in res and res.get("original_filename") == item_filename:
                           file_specific_result = res
                        elif res.get("filename") == item_filename:
                           file_specific_result = res

                    if file_specific_result: # Break if found
                        break
                
                if file_specific_result:
                    print(f"GET_RESULT_LOGIC: Found specific result for file '{item_filename}' in Celery batch {celery_processing_uuid}.")
                    
                    item_data["status"] = "error" if file_specific_result.get("error") else "completed"
                    
                    if item_data["status"] == "error":
                        item_data["message"] = str(file_specific_result.get("error", "Unknown error from Celery task item."))
                        item_data["progress"] = {"current": 100, "total": 100, "message": item_data["message"]}
                    else: # Completed
                        item_data["message"] = "Successfully processed by Celery."
                        item_data["progress"] = {"current": 100, "total": 100, "message": "Completed"}

                    item_data["assessment_details"] = file_specific_result 
                    
                    if 'quality_score' in file_specific_result:
                         item_data['summary_quality_score'] = file_specific_result['quality_score']

                    _assessments_db[str_assessment_id] = item_data
                    _save_assessment_to_redis(str_assessment_id, item_data)
                    _save_assessments_to_file(assessment_id_to_log=str_assessment_id)
                    print(f"GET_RESULT_LOGIC: Updated item {str_assessment_id} from Celery batch. New status: {item_data['status']}")
                else:
                    print(f"GET_RESULT_LOGIC: File '{item_filename}' not found in Celery batch results for {celery_processing_uuid}. Item {str_assessment_id} remains 'pending_celery'.")
            else:
                print(f"GET_RESULT_LOGIC: Celery batch result not yet found in Redis for {redis_key_celery_batch} (linked to item {str_assessment_id}). Item remains 'pending_celery'.")
        
        except redis.exceptions.RedisError as e_redis:
            print(f"GET_RESULT_LOGIC: Redis error for item {str_assessment_id} (Celery UUID {celery_processing_uuid}): {e_redis}")
        except pickle.PickleError as e_pickle:
            print(f"GET_RESULT_LOGIC: Pickle error for item {str_assessment_id} (Celery UUID {celery_processing_uuid}): {e_pickle}")
            item_data["status"] = "error"
            item_data["message"] = "Failed to read Celery result (corrupted data)."
            item_data["progress"] = {"current": 100, "total": 100, "message": "Data corruption error"}
        except Exception as e_general:
            print(f"GET_RESULT_LOGIC: Unexpected error processing 'pending_celery' item {str_assessment_id} (Celery UUID {celery_processing_uuid}): {e_general}")
            traceback.print_exc()
            item_data["status"] = "error"
            item_data["message"] = f"Unexpected error: {str(e_general)[:100]}"
            item_data["progress"] = {"current": 100, "total": 100, "message": "Unexpected processing error"}

    if item_data:
         print(f"GET_RESULT_LOGIC: Returning data for numerical ID {str_assessment_id}, Status: {item_data.get('status')}")
    return item_data

# --- Functions to be developed further --- #

def get_quality_criteria_for_type(document_type: str):
    """Returns the quality assessment tool and criteria items for a given document type."""
    if not document_type or document_type == "Unknown":
        # Potentially return a generic checklist or None
        return None 
    return QUALITY_ASSESSMENT_TOOLS.get(document_type)

MAX_TEXT_SEGMENT_FOR_LLM = 20000 # Reduced for faster processing - 20k chars should be enough

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
    """
    Enhanced parsing of LLM JSON response with comprehensive error handling
    Supports both simple and complex JSON structures from the enhanced prompts
    """
    if not llm_response_raw or not isinstance(llm_response_raw, str):
        return None
    
    try:
        # First try to extract JSON from markdown code blocks
        json_block_match = re.search(r'```json\s*(\{.*?\})\s*```', llm_response_raw, re.DOTALL)
        if json_block_match:
            json_str_to_parse = json_block_match.group(1)
            parsed_json = json.loads(json_str_to_parse)
            return _validate_and_standardize_response(parsed_json)
        
        # Try to find JSON in the raw text
        first_brace = llm_response_raw.find('{')
        last_brace = llm_response_raw.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            potential_json_str = llm_response_raw[first_brace : last_brace + 1]
            parsed_json = json.loads(potential_json_str)
            return _validate_and_standardize_response(parsed_json)
            
        # If no JSON structure found, create a fallback response
        return _create_fallback_response(llm_response_raw)
        
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON from LLM output: {e}. Raw: {llm_response_raw[:200]}")
        return _create_fallback_response(llm_response_raw, error_info=str(e))
    except Exception as e_parse:
        print(f"Unexpected error parsing LLM output: {e_parse}. Raw: {llm_response_raw[:200]}")
        return _create_fallback_response(llm_response_raw, error_info=str(e_parse))

def _validate_and_standardize_response(parsed_json: Dict) -> Dict:
    """
    Validate and standardize the parsed JSON response to ensure required fields
    Enhanced to handle simplified prompt structures while maintaining frontend compatibility
    """
    if not isinstance(parsed_json, dict):
        return _create_fallback_response("Invalid JSON structure")
    
    # Extract the main judgment from various possible fields
    judgment = None
    reason = None
    evidence_quotes = []
    
    # Handle different response structures from different prompt versions
    if "judgment" in parsed_json:
        judgment = parsed_json["judgment"]
    elif "primary_classification" in parsed_json:
        # For document classification responses
        judgment = parsed_json["primary_classification"]
    else:
        judgment = "Error: No judgment found"
    
    # Extract reasoning from various possible fields
    if "reason" in parsed_json:
        reason = parsed_json["reason"]
    elif "justification" in parsed_json:
        reason = parsed_json["justification"]
    elif "evidence_basis" in parsed_json:
        reason = parsed_json["evidence_basis"]
    elif "scoring_rationale" in parsed_json:
        reason = parsed_json["scoring_rationale"]
    elif "classification_reasoning" in parsed_json:
        reason = parsed_json["classification_reasoning"]
    else:
        reason = "No detailed reasoning provided"
    
    # Extract evidence quotes from various possible fields (ensuring frontend compatibility)
    evidence_sources = [
        "evidence_quotes",           # Legacy field
        "supporting_quotes",         # New simplified prompt field
        "supporting_evidence",       # Alternative field
    ]
    
    for source in evidence_sources:
        if source in parsed_json:
            potential_evidence = parsed_json[source]
            if isinstance(potential_evidence, list):
                evidence_quotes = potential_evidence
                break
            elif isinstance(potential_evidence, str) and potential_evidence.strip():
                evidence_quotes = [potential_evidence]
                break
    
    # Ensure evidence_quotes is a list of non-empty strings
    if not isinstance(evidence_quotes, list):
        evidence_quotes = [str(evidence_quotes)] if evidence_quotes else []
    
    # Clean up evidence quotes - remove empty/None values
    evidence_quotes = [quote.strip() for quote in evidence_quotes if quote and str(quote).strip()]
    
    # If no evidence quotes found, create default message
    if not evidence_quotes:
        evidence_quotes = ["Assessment completed but specific evidence quotes not available"]
    
    # Create standardized response for frontend compatibility
    standardized_response = {
        "judgment": judgment,
        "reason": reason,
        "evidence_quotes": evidence_quotes  # Frontend expects this field name
    }
    
    # Preserve additional analysis data if available (for future use or debugging)
    analysis_fields = [
        "reasoning_steps", "amstar2_analysis", "evidence_evaluation", "evidence_analysis",
        "nos_framework", "systematic_search", "star_evaluation", "nos_evaluation",
        "case_control_analysis", "axis_evaluation", "quadas2_analysis", 
        "diagnostic_study_features", "qualitative_assessment", "design_feature_analysis",
        "methodological_verification", "statistical_documentation", "convergent_evidence_assessment",
        "classification_decision", "decision_logic", "confidence_level", "quality_impact", 
        "stars_awarded", "scoring_confidence", "stars_earned", "methodological_assessment",
        "overall_quality", "applicability_concerns", "research_quality", "confidence_assessment",
        "limitations_acknowledged"
    ]
    
    for field in analysis_fields:
        if field in parsed_json:
            standardized_response[field] = parsed_json[field]
    
    return standardized_response

def _create_fallback_response(raw_response: str, error_info: str = None) -> Dict:
    """
    Create a fallback response when JSON parsing fails
    """
    # Try to extract simple judgment from text
    judgment = "Error: Parse Failure"
    if "low risk" in raw_response.lower():
        judgment = "low risk"
    elif "high risk" in raw_response.lower():
        judgment = "high risk"
    elif "some concerns" in raw_response.lower():
        judgment = "some concerns"
    elif "yes" in raw_response.lower():
        judgment = "yes"
    elif "partial yes" in raw_response.lower():
        judgment = "partial yes"
    elif "no" in raw_response.lower():
        judgment = "no"
    elif "star awarded" in raw_response.lower():
        judgment = "star awarded"
    elif "no star" in raw_response.lower():
        judgment = "no star awarded"
    elif "unclear" in raw_response.lower():
        judgment = "unclear"
    
    reason_text = f"Raw response parsing failed. Original content: {raw_response[:200]}..."
    if error_info:
        reason_text += f" Error information: {error_info}"
    
    return {
        "judgment": judgment,
        "reason": reason_text,
        "evidence_quotes": [],
        "parsing_error": True,
        "raw_response": raw_response[:500]  # Keep first 500 chars for debugging
    }

def run_ai_quality_assessment(assessment_id: str, app_context=None, llm_config=None):
    if not llm_config or not llm_config.get("api_key"):
        print(f"Error for {assessment_id}: LLM config missing for background task.")
        if assessment_id in _assessments_db:
            _assessments_db[assessment_id]["status"] = "error"
            _assessments_db[assessment_id]["message"] = "LLM config not provided to worker."
            if "progress" in _assessments_db[assessment_id]: _assessments_db[assessment_id]["progress"]["message"] = "Internal config error."
            _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
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
        import time # time.sleep might be an issue with gevent if not patched, but assuming it is.
        # time.sleep(0.1) # This short sleep is likely fine, or can be gevent.sleep(0.1)

        if not assessment_data:
            print(f"Assessment data for {assessment_id} not found in _execute_assessment_logic.")
            # current_app.logger.error(...) would be better if logger is configured and app_context is robustly handled
            return
        
        if assessment_data.get('assessment_details') is None:
            assessment_data['assessment_details'] = []
            # print(f"EXECUTE_LOGIC: Initialized assessment_details to [] for {assessment_id} as it was None.")

        if assessment_data.get('status') in ['completed', 'error']:
            # print(f"Assessment {assessment_id} already processed ({assessment_data.get('status')}). Skipping.")
            return
        
        # print(f"Background task started for {assessment_id} with provider {llm_config.get('provider_name')}")
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
            assessment_data['message'] = f"No quality assessment tool defined for document type: {document_type}"
            if 'progress' in assessment_data: assessment_data['progress']["message"] = "Tool definition error"
            return

        criteria_list = criteria_tool_info.get("criteria", [])
        if not criteria_list: # Added check for empty criteria list
            assessment_data['status'] = 'completed' # Or 'error' if this is unexpected
            assessment_data['message'] = f"No criteria found for document type: {document_type}. Assessment considered complete."
            if 'progress' in assessment_data: assessment_data['progress']["message"] = "No criteria to assess."
            _save_assessments_to_file(assessment_id_to_log=assessment_id)
            return
            
        total_criteria = len(criteria_list)
        assessment_data['progress']['total'] = total_criteria
        assessment_data['progress']['message'] = f"Spawning assessment tasks for {total_criteria} criteria..."
        
        detailed_results = []
        greenlets_criteria = []
        document_text_segment = text_content[:MAX_TEXT_SEGMENT_FOR_LLM]

        # Local helper function to be spawned as a greenlet
        def assess_one_criterion_task(criterion_item, doc_text_segment, doc_type, p_name, m_id, key, url):
            prompt_struct = _construct_quality_assessment_prompt(
                criterion_text=criterion_item['text'],
                criterion_guidance=criterion_item.get('guidance'),
                document_text_segment=doc_text_segment,
                document_type=doc_type
            )
            try:
                raw_response = call_llm_api_raw_content(
                    prompt_struct, p_name, m_id, key, url, max_tokens_override=300
                )
                parsed_resp = _parse_llm_json_response(raw_response)
                if parsed_resp and isinstance(parsed_resp, dict):
                    return {
                        "criterion_id": criterion_item['id'], "criterion_text": criterion_item['text'],
                        "judgment": parsed_resp.get("judgment", "Error: Missing judgment"),
                        "reason": parsed_resp.get("reason", "Error: Missing reason"),
                        "evidence_quotes": parsed_resp.get("evidence_quotes", [])
                    }
                else:
                    return {"criterion_id": criterion_item['id'], "criterion_text": criterion_item['text'], "judgment": "Error: Parse Failure", "reason": f"Raw: {raw_response[:100] if raw_response else 'None'}...", "evidence_quotes": []}
            except Exception as e_llm:
                return {"criterion_id": criterion_item['id'], "criterion_text": criterion_item['text'], "judgment": "Error: API Call Failed", "reason": str(e_llm), "evidence_quotes": []}

        for i, criterion_obj in enumerate(criteria_list):
            # Update progress before spawning, conceptually tied to starting this criterion's processing
            # assessment_data['progress']['current'] = i + 1 # Progress will be updated when retrieving results
            # assessment_data['progress']['message'] = f"Queuing criterion {i+1}/{total_criteria}: {criterion_obj['text'][:30]}..."
            # print(f"  Thread for {assessment_id}: Queuing {criterion_obj['text'][:30]}...") # Using print for now, as app_logger might not be context-safe here
            
            g = spawn(assess_one_criterion_task, criterion_obj, document_text_segment, document_type,
                      provider_name, model_id, api_key, base_url)
            greenlets_criteria.append({'greenlet': g, 'original_criterion': criterion_obj, 'index': i})
        
        # Gunicorn worker timeout is 3600s. Nginx for / may be 120s or 3600s.
        # This task runs in app.executor (ThreadPool) which is not directly tied to request timeout.
        # However, we should set a reasonable timeout for all criteria processing.
        join_timeout_qa = 3500 # e.g., slightly less than Gunicorn default, or based on expected max time per document
        # print(f"QA Service {assessment_id}: Waiting for {len(greenlets_criteria)} criteria greenlets with timeout {join_timeout_qa}s.")
        joinall([item['greenlet'] for item in greenlets_criteria], timeout=join_timeout_qa)
        # print(f"QA Service {assessment_id}: Criteria greenlets join completed or timed out.")

        temp_results_map = {} # Using a map to ensure order if needed, or can append directly if order is by completion
        processed_criteria_count = 0

        for item_info in greenlets_criteria:
            glet = item_info['greenlet']
            original_crit = item_info['original_criterion']
            original_idx = item_info['index']
            crit_result_data = None
            processed_criteria_count +=1
            
            assessment_data['progress']['current'] = processed_criteria_count
            assessment_data['progress']['message'] = f"Processing result for criterion {processed_criteria_count}/{total_criteria}: {original_crit['text'][:30]}..."

            try:
                if glet.ready():
                    if glet.successful():
                        crit_result_data = glet.get(block=False)
                    else:
                        # print(f"QA Service: Unhandled exception in greenlet for criterion {original_crit['id']}: {glet.exception}")
                        crit_result_data = {"criterion_id": original_crit['id'], "criterion_text": original_crit['text'], "judgment": "Error: Greenlet Exception", "reason": str(glet.exception), "evidence_quotes": []}
                else:
                    # print(f"QA Service: Greenlet for criterion {original_crit['id']} timed out.")
                    crit_result_data = {"criterion_id": original_crit['id'], "criterion_text": original_crit['text'], "judgment": "Error: Criterion Timeout", "reason": "Processing for this criterion timed out.", "evidence_quotes": []}
            except Exception as exc_glet_get:
                # print(f"QA Service: Exception getting result from greenlet for criterion {original_crit['id']}: {exc_glet_get}")
                crit_result_data = {"criterion_id": original_crit['id'], "criterion_text": original_crit['text'], "judgment": "Error: Result Retrieval", "reason": str(exc_glet_get), "evidence_quotes": []}
            
            temp_results_map[original_idx] = crit_result_data

        # Reconstruct detailed_results in original order
        for i in range(total_criteria):
            res = temp_results_map.get(i)
            if res:
                detailed_results.append(res)
            else:
                # This case should ideally not happen if all indices are processed
                detailed_results.append({
                    "criterion_id": criteria_list[i]['id'], "criterion_text": criteria_list[i]['text'],
                    "judgment": "Error: Processing Skipped", "reason": "Result for this criterion was not found after gevent processing.", "evidence_quotes": []
                })

        assessment_data['assessment_details'] = detailed_results
        assessment_data['status'] = 'completed'
        assessment_data['progress']['message'] = "Assessment completed!"
        assessment_data['progress']['current'] = total_criteria # Ensure current shows total at the end

        negative_judgment_count = 0
        if detailed_results:
            for res_item in detailed_results:
                judgment = res_item.get("judgment", "").lower()
                if "no" in judgment or "high risk" in judgment or "poor" in judgment or judgment == "not met" or "error" in judgment.lower(): # Count errors as negative
                    negative_judgment_count += 1
        assessment_data['summary_negative_findings'] = negative_judgment_count
        assessment_data['summary_total_criteria_evaluated'] = total_criteria
        
        if assessment_id in _assessments_db:
            _assessments_db[assessment_id] = assessment_data

        _save_assessment_to_redis(assessment_id, assessment_data)
        _save_assessments_to_file(assessment_id_to_log=assessment_id)
        # print(f"Background task for {assessment_id} finished. Results: {len(detailed_results)}")

    except Exception as e_outer:
        print(f"CRITICAL ERROR in _execute_assessment_logic for {assessment_id}: {e_outer}")
        traceback.print_exc()
        if assessment_id in _assessments_db and _assessments_db[assessment_id] is not None:
            _assessments_db[assessment_id]['status'] = 'error'
            _assessments_db[assessment_id]['message'] = f"Critical background task error: {str(e_outer)[:100]}"
            if 'progress' in _assessments_db[assessment_id] and _assessments_db[assessment_id]['progress'] is not None:
                 _assessments_db[assessment_id]['progress']['message'] = "Critical error during processing"
            _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
            _save_assessments_to_file(assessment_id_to_log=assessment_id)

def quick_upload_document(pdf_file_stream, original_filename: str, selected_document_type: str = None):
    """
    Quick upload mode: Only save PDF file, create assessment record, return ID immediately
    Text extraction and AI assessment happen asynchronously in background for instant response
    """
    # Use safe ID generation to prevent concurrent access issues
    assessment_id = _generate_safe_assessment_id()
    
    saved_pdf_filename = None
    saved_pdf_full_path = None
    
    # 1. Quickly save PDF file
    try:
        pdf_file_stream.seek(0)
        secure_original_filename = secure_filename(original_filename)
        saved_pdf_filename = f"{assessment_id}_{secure_original_filename}"
        saved_pdf_full_path = os.path.join(QA_PDF_UPLOAD_DIR, saved_pdf_filename)
        
        with open(saved_pdf_full_path, 'wb') as f_out:
            pdf_file_stream.seek(0)
            f_out.write(pdf_file_stream.read())
        
        print(f"QUICK_UPLOAD: PDF for assessment {assessment_id} saved to: {saved_pdf_full_path}")
        
    except Exception as e_save:
        print(f"QUICK_UPLOAD_ERROR: Error saving PDF for assessment {assessment_id}: {e_save}")
        _assessments_db[assessment_id] = {
            "status": "error", 
            "message": f"File save failed: {e_save}", 
            "filename": original_filename,
            "progress": {"current": 0, "total": 100, "message": "File save error"}
        }
        _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
        return assessment_id

    # 2. Create initial assessment record (without text extraction)
    document_type_to_store = selected_document_type or "Unknown"
    
    _assessments_db[assessment_id] = {
        "status": "pending_text_extraction", 
        "filename": original_filename,
        "document_type": document_type_to_store,
        "text_preview": "File uploaded successfully, text extraction in progress...",
        "raw_text": None,  # Will be populated during background processing
        "assessment_details": None,
        "user_review": None,
        "classification_evidence": None,
        "saved_pdf_filename": saved_pdf_filename,
        "saved_pdf_full_path": saved_pdf_full_path,  # Needed for background processing
        "progress": {"current": 10, "total": 100, "message": "File uploaded, preparing text extraction..."}
    }
    
    # 3. Immediately save to Redis and file
    _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
    _save_assessments_to_file(assessment_id_to_log=assessment_id)
    
    print(f"QUICK_UPLOAD: Assessment {assessment_id} created successfully. Status: pending_text_extraction")
    
    # 4. Start background processing (async text extraction and AI assessment)
    try:
        # Get LLM configuration
        from flask import session
        current_llm_main_config = get_current_llm_config(session)
        provider_name = current_llm_main_config['provider_name']
        api_key_val = get_api_key_for_provider(provider_name, session)
        if not api_key_val:
            raise ValueError(f"API Key for {provider_name} not found in session or environment.")
        
        llm_config_for_task = {
            "provider_name": provider_name,
            "model_id": current_llm_main_config['model_id'],
            "base_url": get_base_url_for_provider(provider_name),
            "api_key": api_key_val
        }
        
        # Start background processing
        spawn(run_background_processing, assessment_id, current_app._get_current_object(), llm_config_for_task)
        print(f"QUICK_UPLOAD: Background processing task for {assessment_id} started")
        
    except Exception as e_bg:
        print(f"QUICK_UPLOAD_ERROR: Failed to start background processing for {assessment_id}: {e_bg}")
        _assessments_db[assessment_id]["status"] = "error"
        _assessments_db[assessment_id]["message"] = f"Failed to start background processing: {e_bg}"
        _assessments_db[assessment_id]["progress"]["message"] = "Failed to start background processing"
        _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
    
    return assessment_id

def run_background_processing(assessment_id: str, app_context=None, llm_config=None):
    """
    Background processing: Text extraction + Document classification + AI quality assessment
    Performed in stages, with progress updates for each stage
    """
    if app_context:
        with app_context.app_context():
            _execute_background_processing(assessment_id, llm_config)
    else:
        print(f"Warning for {assessment_id}: Running background processing without explicit app context.")
        _execute_background_processing(assessment_id, llm_config)

def _execute_background_processing(assessment_id: str, llm_config: Dict):
    """Execute the specific logic for background processing"""
    try:
        assessment_data = _assessments_db.get(assessment_id)
        if not assessment_data:
            print(f"BACKGROUND_PROC: Assessment data for {assessment_id} not found.")
            return
        
        if assessment_data.get('status') not in ['pending_text_extraction']:
            print(f"BACKGROUND_PROC: Assessment {assessment_id} status is {assessment_data.get('status')}, skipping background processing.")
            return
        
        # Stage 1: Text extraction (20-40%)
        print(f"BACKGROUND_PROC: Starting text extraction for {assessment_id}")
        assessment_data['progress'] = {"current": 20, "total": 100, "message": "Extracting PDF text..."}
        _save_assessment_to_redis(assessment_id, assessment_data)
        
        saved_pdf_full_path = assessment_data.get('saved_pdf_full_path')
        if not saved_pdf_full_path or not os.path.exists(saved_pdf_full_path):
            raise Exception("PDF file not found, cannot perform text extraction")
        
        # Read PDF file and extract text
        with open(saved_pdf_full_path, 'rb') as pdf_file:
            text_content = extract_text_from_pdf(pdf_file, ocr_language='eng')
        
        if not text_content:
            raise Exception("PDF text extraction result is empty")
        
        assessment_data['raw_text'] = text_content
        assessment_data['text_preview'] = text_content[:500] + ("..." if len(text_content) > 500 else "")
        assessment_data['progress'] = {"current": 40, "total": 100, "message": "Text extraction completed, starting document classification..."}
        _save_assessment_to_redis(assessment_id, assessment_data)
        
        print(f"BACKGROUND_PROC: Text extraction completed for {assessment_id}, length: {len(text_content)}")
        
        # Stage 2: Document classification (40-60%)
        document_type_to_store = assessment_data.get('document_type')
        classification_evidence = None
        
        if not document_type_to_store or document_type_to_store == "Unknown":
            try:
                assessment_data['progress'] = {"current": 50, "total": 100, "message": "Performing document type classification..."}
                _save_assessment_to_redis(assessment_id, assessment_data)
                
                detected_type, type_scores = classify_document_type(text_content)
                if detected_type and detected_type != "Unknown" and detected_type != "Uncertain":
                    document_type_to_store = detected_type
                    classification_evidence = get_document_evidence(text_content, detected_type)
                    print(f"BACKGROUND_PROC: Document {assessment_id} classified as: {document_type_to_store}")
                else:
                    document_type_to_store = "Unknown"
                    print(f"BACKGROUND_PROC: Document {assessment_id} could not be classified. Scores: {type_scores}")
            except Exception as classify_error:
                print(f"BACKGROUND_PROC: Error during document classification for {assessment_id}: {classify_error}")
                document_type_to_store = "Unknown"
        
        assessment_data['document_type'] = document_type_to_store
        assessment_data['classification_evidence'] = classification_evidence
        assessment_data['progress'] = {"current": 60, "total": 100, "message": f"Classification completed: {document_type_to_store}, starting quality assessment..."}
        _save_assessment_to_redis(assessment_id, assessment_data)
        
        # Stage 3: Quality assessment (60-100%)
        if document_type_to_store in QUALITY_ASSESSMENT_TOOLS:
            assessment_data['status'] = 'processing_assessment'
            assessment_data['progress'] = {"current": 70, "total": 100, "message": "Performing AI quality assessment..."}
            _save_assessment_to_redis(assessment_id, assessment_data)
            
            # Call existing AI assessment logic
            _execute_assessment_logic(assessment_id, llm_config)
        else:
            # Unsupported document type, mark as completed but without assessment
            assessment_data['status'] = 'completed'
            assessment_data['message'] = f"Document type '{document_type_to_store}' is not currently supported for quality assessment"
            assessment_data['progress'] = {"current": 100, "total": 100, "message": "Processing completed (document type not supported for assessment)"}
            assessment_data['assessment_details'] = []
            _save_assessment_to_redis(assessment_id, assessment_data)
            _save_assessments_to_file(assessment_id_to_log=assessment_id)
        
        print(f"BACKGROUND_PROC: Background processing completed for {assessment_id}")
        
    except Exception as e_bg:
        print(f"BACKGROUND_PROC_ERROR: Critical error in background processing for {assessment_id}: {e_bg}")
        traceback.print_exc()
        if assessment_id in _assessments_db:
            _assessments_db[assessment_id]['status'] = 'error'
            _assessments_db[assessment_id]['message'] = f"Background processing error: {str(e_bg)[:100]}"
            _assessments_db[assessment_id]['progress'] = {"current": 100, "total": 100, "message": "Processing failed"}
            _save_assessment_to_redis(assessment_id, _assessments_db[assessment_id])
            _save_assessments_to_file(assessment_id_to_log=assessment_id)

# Example of how you might call the assessment after processing:
# if assessment_id and _assessments_db[assessment_id]['status'] == 'pending':
#     run_ai_quality_assessment(assessment_id) 