import os
import pandas as pd
import time
import datetime  # Explicitly import datetime for current year
import uuid
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.metrics import confusion_matrix, cohen_kappa_score, f1_score, precision_score, recall_score, \
    multilabel_confusion_matrix
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response, send_file
from werkzeug.utils import secure_filename
import traceback
import json  # For SSE
import sys # For printing to stderr
import io # For creating in-memory files
import re
from typing import Dict, Optional # ADDED Import for type hints
from cachetools import TTLCache # <-- Import TTLCache
import logging # <-- Import logging

# --- Configure logging ---
logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO").upper(), # Allow setting log level via env var
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # Log to stdout
    ]
)
app_logger = logging.getLogger("metascreener_app") # Use a specific name for the app logger
# --- End logging configuration ---

# Import functions from our utils and config
from utils import load_literature_ris, extract_text_from_pdf, construct_llm_prompt, call_llm_api, call_llm_api_raw_content, _parse_llm_response
from config import (
    get_screening_criteria, set_user_criteria, reset_to_default_criteria,
    DEFAULT_EXAMPLE_CRITERIA, USER_CRITERIA,
    get_llm_providers_info, get_current_llm_config,
    get_api_key_for_provider, get_base_url_for_provider,
    DEFAULT_SYSTEM_PROMPT, DEFAULT_OUTPUT_INSTRUCTIONS,
    get_current_criteria_object
)

app = Flask(__name__)
app.secret_key = os.urandom(24)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'ris'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
test_sessions = {} # For holding test screening data + results before metrics
full_screening_sessions = {} # ADDED: For holding full screening results temporarily
# NEW: Use TTLCache for pdf_screening_results. Max 500 items, 2 hours TTL (7200 seconds)
pdf_screening_results = TTLCache(maxsize=500, ttl=7200)
pdf_extraction_results = {} # ADDED: For extraction results
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# --- ADDED: Helper function to parse line ranges ---
def parse_line_range(range_str: str, max_items: int) -> tuple[int, int]:
    """
    Parses a 1-based range string (e.g., "5-10", "7", "5-", "-10") 
    into 0-based start (inclusive) and end (exclusive) indices for DataFrame iloc.
    max_items is the total number of items in the DataFrame.
    """
    if not range_str:
        raise ValueError("Range string cannot be empty.")

    range_str = range_str.strip()
    start_1_based_str, end_1_based_str = "", ""

    if '-' in range_str:
        parts = range_str.split('-', 1)
        start_1_based_str = parts[0].strip()
        end_1_based_str = parts[1].strip()

        if not start_1_based_str and not end_1_based_str: # User typed just "-"
            raise ValueError("Invalid range format '-'. Use 'N-M', 'N-', '-M', or 'N'.")
    else: # Single number
        start_1_based_str = range_str
        end_1_based_str = range_str # screen only this single line

    try:
        if not start_1_based_str: # Format like "-10"
            start_1_based = 1
        else:
            start_1_based = int(start_1_based_str)

        if not end_1_based_str: # Format like "5-"
            end_1_based = max_items
        else:
            end_1_based = int(end_1_based_str)
    except ValueError:
        raise ValueError("Invalid number in range. Please use digits (e.g., '5-10' or '7').")

    if start_1_based <= 0 or end_1_based <= 0:
        raise ValueError("Line numbers must be positive.")
    if start_1_based > end_1_based:
        raise ValueError(f"Start of range ({start_1_based}) cannot be after end ({end_1_based}).")
    
    # Cap end_1_based at max_items, but ensure start is not beyond max_items already
    if start_1_based > max_items:
        raise ValueError(f"Start of range ({start_1_based}) is beyond the total number of available items ({max_items}).")
    
    end_1_based = min(end_1_based, max_items)

    # Convert to 0-based for iloc: start is inclusive, end is exclusive
    # User "1" (item 1) is df.iloc[0]. User "1-3" (items 1,2,3) is df.iloc[0:3]
    start_0_based = start_1_based - 1
    end_0_based_exclusive = end_1_based 

    return start_0_based, end_0_based_exclusive
# --- END Helper function ---


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# --- Route for LLM Configuration ---
@app.route('/configure_llm', methods=['POST'])
def configure_llm():
    app_logger.info("--- Entering configure_llm --- ")
    selected_provider = request.form.get('llm_provider')
    selected_model_id = request.form.get('llm_model_id')
    app_logger.info(f"Provider: {selected_provider}, Model: {selected_model_id}")

    providers_info = get_llm_providers_info()
    if selected_provider not in providers_info:
        flash('Invalid LLM Provider selected.', 'error')
        return redirect(url_for('llm_config_page'))

    provider_config = providers_info[selected_provider]

    session['selected_llm_provider'] = selected_provider
    session['selected_llm_model_id'] = selected_model_id

    api_key_form_field = f"{selected_provider.lower()}_api_key"
    user_api_key = request.form.get(api_key_form_field)
    app_logger.debug(f"Form field for key: '{api_key_form_field}'")
    app_logger.debug(f"Submitted key value: '{user_api_key}' (Type: {type(user_api_key)})")

    if user_api_key:
        app_logger.debug("User API key is truthy, attempting to save...")
        session_key_for_api = provider_config.get("api_key_session_key")
        app_logger.debug(f"Session key name from config: '{session_key_for_api}'")
        if session_key_for_api:
            session[session_key_for_api] = user_api_key
            app_logger.info(f"Saved API key for {selected_provider} (first 5 chars: '{user_api_key[:5]}...') to session['{session_key_for_api}']")
            flash(f'API Key for {selected_provider} updated in session.', 'info')
        else:
             app_logger.error("Could not find api_key_session_key in provider config!")
    else:
        app_logger.debug("User API key is FALSY (empty or None), NOT saving to session.")
        if not user_api_key and request.form.get(f'clear_{api_key_form_field}'):
             session_key_for_api = provider_config.get("api_key_session_key")
             if session_key_for_api and session_key_for_api in session:
                 session.pop(session_key_for_api)
                 app_logger.info(f"Cleared key for {selected_provider} from session.")
                 flash(f'API Key for {selected_provider} cleared from session.', 'info')

    app_logger.debug(f"Session contents after configure_llm: {session}")
    flash(f'LLM configuration updated to {selected_provider} - Model: {selected_model_id}.', 'success')
    return redirect(url_for('llm_config_page'))


@app.route('/get_models_for_provider/<provider_name>')
def get_models_for_provider_route(provider_name):
    providers_info = get_llm_providers_info()
    if provider_name in providers_info:
        return jsonify(providers_info[provider_name]["models"])
    return jsonify([])


# --- Main Route ---
@app.route('/')
def index():
    return redirect(url_for('llm_config_page'))


# --- New Page Routes ---
@app.route('/llm_config', methods=['GET'], endpoint='llm_config_page')
def llm_config_page():
    llm_providers_info = get_llm_providers_info()
    current_llm = get_current_llm_config(session)
    api_key_status = {}
    for p_name, p_data in llm_providers_info.items():
        key_in_session = False
        key_in_env = False
        session_key_name = p_data.get("api_key_session_key")
        env_key_name = p_data.get("api_key_env_var")

        if session_key_name and session_key_name in session and session[session_key_name]:
            key_in_session = True
        if env_key_name and os.getenv(env_key_name):
            key_in_env = True

        if key_in_session:
            api_key_status[p_name] = "Set in session"
        elif key_in_env:
            api_key_status[p_name] = "Using environment default"
        else:
            api_key_status[p_name] = "Not set"
    
    current_year = datetime.datetime.now().year
    return render_template('llm_configuration.html',
                           llm_providers_info=llm_providers_info,
                           current_llm_provider=current_llm['provider_name'],
                           current_llm_model_id=current_llm['model_id'],
                           api_key_status=api_key_status,
                           current_year=current_year)

@app.route('/criteria', methods=['GET'], endpoint='screening_criteria_page')
def screening_criteria_page():
    criteria = get_current_criteria_object()
    current_year = datetime.datetime.now().year
    # Pass defaults for the template to use if user hasn't set custom ones
    config_defaults = {
        'DEFAULT_SYSTEM_PROMPT': DEFAULT_SYSTEM_PROMPT,
        'DEFAULT_OUTPUT_INSTRUCTIONS': DEFAULT_OUTPUT_INSTRUCTIONS
    }
    return render_template('screening_criteria.html', 
                           criteria=criteria, 
                           current_year=current_year,
                           config_defaults=config_defaults) # Pass defaults to template

@app.route('/abstract_screening', methods=['GET'], endpoint='abstract_screening_page')
def abstract_screening_page():
    current_year = datetime.datetime.now().year
    return render_template('abstract_screening.html', current_year=current_year)

@app.route('/full_text_screening', methods=['GET'], endpoint='full_text_screening_page')
def full_text_screening_page():
    current_year = datetime.datetime.now().year
    return render_template('full_text_screening.html', current_year=current_year)

@app.route('/screening_actions', methods=['GET'], endpoint='screening_actions_page') # Corrected route name for consistency
def screening_actions_page():
    # This page will need current_year and potentially LLM info if displayed directly
    current_year = datetime.datetime.now().year
    # If we need to show current LLM on this page, fetch it:
    # current_llm = get_current_llm_config(session) 
    return render_template('screening_actions.html', 
                           current_year=current_year)
                           # current_llm_provider=current_llm['provider_name'] # if needed


# --- Criteria Routes ---
@app.route('/set_criteria', methods=['POST'])
def set_criteria():
    try:
        # Get NEW structured criteria fields including _maybe
        criteria_dict = {
            # PICOT Include/Exclude/Maybe
            'p_include': request.form.get('p_include', ''),
            'p_exclude': request.form.get('p_exclude', ''),
            'p_maybe': request.form.get('p_maybe', ''), # Added
            'i_include': request.form.get('i_include', ''),
            'i_exclude': request.form.get('i_exclude', ''),
            'i_maybe': request.form.get('i_maybe', ''), # Added
            'c_include': request.form.get('c_include', ''),
            'c_exclude': request.form.get('c_exclude', ''),
            'c_maybe': request.form.get('c_maybe', ''), # Added
            'o_include': request.form.get('o_include', ''),
            'o_exclude': request.form.get('o_exclude', ''),
            'o_maybe': request.form.get('o_maybe', ''), # Added
            't_include': request.form.get('t_include', ''),
            't_exclude': request.form.get('t_exclude', ''),
            't_maybe': request.form.get('t_maybe', ''), # Added
            # Other Criteria
            'other_inclusion': request.form.get('other_inclusion', ''), 
            'other_exclusion': request.form.get('other_exclusion', ''), 
            # REMOVED: 'maybe_conditions': request.form.get('maybe_conditions', ''),
        }
        
        # Get advanced settings (unchanged)
        system_prompt = request.form.get('ai_system_prompt')
        output_instructions = request.form.get('ai_output_format_instructions')
        if system_prompt is not None: criteria_dict['ai_system_prompt'] = system_prompt
        if output_instructions is not None: criteria_dict['ai_output_format_instructions'] = output_instructions

        set_user_criteria(criteria_dict) # Update the global USER_CRITERIA
        flash('Screening criteria and settings successfully saved!', 'success')
    except Exception as e:
        flash(f'Error saving screening criteria: {e}', 'error')
        app_logger.exception("Error saving screening criteria") # Replaces traceback.print_exc()
    return redirect(url_for('screening_criteria_page'))


@app.route('/reset_criteria')
def reset_criteria():
    reset_to_default_criteria()
    flash('Screening criteria have been reset to default values.', 'info')
    return redirect(url_for('screening_criteria_page')) # MODIFIED REDIRECT


# --- Screening Logic Helper ---
def _perform_screening_on_abstract(abstract_text, criteria_prompt_text, provider_name, model_id, api_key, base_url):
    # Check if essential config is provided (already checked before calling usually, but good safeguard)
    if not api_key:
        # This case should ideally be caught before calling this helper
        return {"decision": "CONFIG_ERROR", "reasoning": f"API Key for {provider_name} missing in call."}

    ai_decision = "ERROR"
    ai_reasoning = "An unexpected error occurred during AI screening."

    if pd.isna(abstract_text) or not abstract_text or not isinstance(abstract_text, str) or abstract_text.strip() == "":
        ai_decision = "NO_ABSTRACT"
        ai_reasoning = "Abstract is missing or empty."
    else:
        prompt = construct_llm_prompt(abstract_text, criteria_prompt_text)
        if prompt:
            # Use passed-in parameters for the API call
            api_result = call_llm_api(prompt, provider_name, model_id, api_key, base_url)

            if api_result and isinstance(api_result, dict):
                ai_decision = api_result.get('label', 'API_ERROR')
                ai_reasoning = api_result.get('justification', 'API call failed or returned invalid data.')
            else:
                ai_decision = "API_ERROR"
                ai_reasoning = "API call function returned None or malformed data structure."
        else:
            ai_decision = "PROMPT_ERROR"
            ai_reasoning = "Failed to construct LLM prompt."

    return {"decision": ai_decision, "reasoning": ai_reasoning}


# --- Screening Routes ---
@app.route('/test_screening', methods=['POST'], endpoint='test_screening')
def test_screening():
    # Option 1: Disable this route completely
    flash("Test screening is now handled via the progress button.", "info")
    return redirect(url_for('abstract_screening_page'))
    # Option 2: Keep it as a non-SSE fallback (less ideal now)
    # Option 3: Remove it entirely if the button is gone / SSE is stable


@app.route('/screen_full_dataset/<session_id>')
def screen_full_dataset(session_id):
    if not session_id or session_id not in test_sessions: flash('Test session not found or expired.', 'error'); return redirect(url_for('abstract_screening_page'))
    session_data = test_sessions.get(session_id)
    if not session_data: flash('Test session data missing.', 'error'); return redirect(url_for('abstract_screening_page'))
    df = session_data['df']; filename = session_data['file_name']
    results_list = []
    try:
        criteria_prompt_text = get_screening_criteria()
        current_llm_config_data = get_current_llm_config(session)
        provider_name = current_llm_config_data['provider_name']
        model_id = current_llm_config_data['model_id']
        base_url = get_base_url_for_provider(provider_name)
        provider_info = get_llm_providers_info().get(provider_name, {})
        session_key_name = provider_info.get("api_key_session_key")
        api_key = session.get(session_key_name) if session_key_name else None
        if not api_key: flash(f"API Key for {provider_name} must be provided via the configuration form for this session.", "error"); return redirect(url_for('llm_config_page'))

        results_map = {} # To store results keyed by index
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_index = {}
            futures = []
            for index, row in df.iterrows():
                abstract = row.get('abstract')
                future = executor.submit(
                     _perform_screening_on_abstract,
                     abstract, criteria_prompt_text,
                     provider_name, model_id, api_key, base_url
                 )
                futures.append(future)
                future_to_index[future] = index # Map future back to original index

            # Process as completed to handle errors gracefully
            for future in as_completed(futures):
                index = future_to_index[future]
                try:
                    screening_result = future.result()
                    if screening_result['decision'] == "CONFIG_ERROR":
                         flash(f"Config error for item at index {index}: {screening_result['reasoning']}", "error")
                         if session_id in test_sessions: del test_sessions[session_id]
                         return redirect(url_for('llm_config_page'))
                    results_map[index] = screening_result # Store result associated with its original index
                except Exception as exc:
                     app_logger.error(f"Error processing item (index {index}) in sync route: {exc}")
                     traceback.print_exc()
                     results_map[index] = {'decision': 'WORKER_ERROR', 'reasoning': str(exc)} # Store an error result

        # Reconstruct results_list in original order
        for index, row in df.iterrows():
             result_data = results_map.get(index)
             if result_data:
                  results_list.append({
                      'index': index + 1,
                      'title': row.get('title', "N/A"),
                      'authors': ", ".join(row.get('authors', [])) if row.get('authors') else "Authors Not Found",
                      'decision': result_data['decision'],
                      'reasoning': result_data['reasoning']
                  })

        if session_id in test_sessions: del test_sessions[session_id]
        current_year = datetime.datetime.now().year
        return render_template('results.html', results=results_list, filename=filename, current_year=current_year)

    except Exception as e:
        app_logger.exception(f"Error during full screening for session {session_id}")
        flash(f"Error during full screening: {e}.", 'error')
        if session_id in test_sessions:
            del test_sessions[session_id]
        return redirect(url_for('abstract_screening_page'))


# --- Metrics Calculation (Updated) ---
def calculate_performance_metrics(ai_decisions, human_decisions, labels_order=['INCLUDE', 'MAYBE', 'EXCLUDE']):
    # Added check for pandas import, assuming it might be needed here
    try: import pandas as pd
    except ImportError: print("Pandas not found, Kappa NaN check might fail."); pd=None

    if not ai_decisions or not human_decisions or len(ai_decisions) != len(human_decisions):
        # Return structure consistent with the successful case, but with empty/zero values
        default_matrix = {
            'labels': labels_order,
            'matrix_data': [[0]*len(labels_order) for _ in range(len(labels_order))] # Use matrix_data key
        }
        default_metrics = {
            'cohens_kappa': 0, 'overall_accuracy': 0, 'workload_reduction': 0, 'discrepancy_rate': 0,
            'sensitivity_include': 0, 'precision_include': 0, 'f1_include': 0, 'specificity_for_include_task': 0,
            'ai_maybe_rate': 0, 'human_maybe_rate': 0, 'total_compared': 0
        }
        default_class_metrics = {label: {'precision': 0, 'recall': 0, 'f1_score': 0, 'tp':0, 'fp':0, 'fn':0, 'specificity': 0} for label in labels_order}
        default_maybe_res = {
             'ai_maybe_to_human_include': 0, 'ai_maybe_to_human_exclude': 0, 'ai_maybe_to_human_maybe': 0,
             'human_maybe_to_ai_include': 0, 'human_maybe_to_ai_exclude': 0
        }
        return {
            'metrics': default_metrics, 'matrix_3x3': default_matrix,
            'class_metrics': default_class_metrics, 'maybe_resolution': default_maybe_res
        }


    y_true = pd.Series(human_decisions, dtype="category").cat.set_categories(labels_order, ordered=True)
    y_pred = pd.Series(ai_decisions, dtype="category").cat.set_categories(labels_order, ordered=True)

    cm_3x3 = confusion_matrix(y_true, y_pred, labels=labels_order)
    # Use 'matrix_data' as the key instead of 'values' to avoid potential conflict
    cm_3x3_dict = {"labels": labels_order, "matrix_data": cm_3x3.tolist()}

    kappa = cohen_kappa_score(y_true, y_pred, labels=labels_order)
    if pd and pd.isna(kappa): kappa = 0.0

    correct_predictions = (y_true == y_pred).sum()
    total_predictions = len(y_true)
    overall_accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0

    mcm = multilabel_confusion_matrix(y_true, y_pred, labels=labels_order)
    class_metrics = {}
    for i, label in enumerate(labels_order):
        tn, fp, fn, tp = mcm[i].ravel()
        precision_val = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall_val = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1_val = 0
        if (precision_val + recall_val) > 0:
            f1_val = 2 * (precision_val * recall_val) / (precision_val + recall_val)
        specificity_val = tn / (tn + fp) if (tn + fp) > 0 else 0 # Calculate specificity here
        class_metrics[label] = {
            'precision': precision_val, 
            'recall': recall_val, 
            'f1_score': f1_val,
            'specificity': specificity_val, # Store specificity per class
            'tp': int(tp), 'tn': int(tn), 'fp': int(fp), 'fn': int(fn)
        }

    y_true_binary_include = [1 if d == 'INCLUDE' else 0 for d in human_decisions]
    y_pred_binary_include = [1 if d == 'INCLUDE' else 0 for d in ai_decisions]
    sensitivity_include = recall_score(y_true_binary_include, y_pred_binary_include, pos_label=1, zero_division=0)
    precision_include = precision_score(y_true_binary_include, y_pred_binary_include, pos_label=1, zero_division=0)
    f1_include = f1_score(y_true_binary_include, y_pred_binary_include, pos_label=1, zero_division=0)

    cm_binary_std = confusion_matrix(y_true_binary_include, y_pred_binary_include, labels=[0, 1])
    specificity_for_include_task = 0
    if cm_binary_std.size == 4:
        tn_std, fp_std, fn_std, tp_std = cm_binary_std.ravel()
        if (tn_std + fp_std) > 0: specificity_for_include_task = tn_std / (tn_std + fp_std)
    elif len(set(y_true_binary_include)) == 1 and y_true_binary_include[0] == 0 and \
            len(set(y_pred_binary_include)) == 1 and y_pred_binary_include[0] == 0:
        # Handle case where all are correctly negative in the binary include task
        specificity_for_include_task = 1.0 

    true_negatives_for_workload = class_metrics.get('EXCLUDE', {}).get('tp', 0)
    workload_reduction = (true_negatives_for_workload / total_predictions) * 100 if total_predictions > 0 else 0
    discrepancy_rate = (1 - overall_accuracy) * 100

    ai_maybe_rate = sum(1 for d in ai_decisions if d == 'MAYBE') / total_predictions if total_predictions > 0 else 0
    human_maybe_rate = sum(
        1 for d in human_decisions if d == 'MAYBE') / total_predictions if total_predictions > 0 else 0

    maybe_resolution_metrics = {
        'ai_maybe_to_human_include': sum(
            1 for ai, h in zip(ai_decisions, human_decisions) if ai == 'MAYBE' and h == 'INCLUDE'),
        'ai_maybe_to_human_exclude': sum(
            1 for ai, h in zip(ai_decisions, human_decisions) if ai == 'MAYBE' and h == 'EXCLUDE'),
        'ai_maybe_to_human_maybe': sum(
            1 for ai, h in zip(ai_decisions, human_decisions) if ai == 'MAYBE' and h == 'MAYBE'),
        'human_maybe_to_ai_include': sum(
            1 for ai, h in zip(ai_decisions, human_decisions) if h == 'MAYBE' and ai == 'INCLUDE'),
        'human_maybe_to_ai_exclude': sum(
            1 for ai, h in zip(ai_decisions, human_decisions) if h == 'MAYBE' and ai == 'EXCLUDE'),
    }

    # --- ADDED: Critical Error Rate (I -> E) Calculation --- 
    critical_errors_count = 0
    try:
        # Find indices for INCLUDE and EXCLUDE in labels_order
        idx_include = labels_order.index('INCLUDE')
        idx_exclude = labels_order.index('EXCLUDE')
        # Get count from confusion matrix where Human=INCLUDE (row idx_include) and AI=EXCLUDE (column idx_exclude)
        critical_errors_count = cm_3x3[idx_include, idx_exclude]
    except (ValueError, IndexError) as e:
        app_logger.error(f"Error calculating critical error count: {e}")
        critical_errors_count = 0 # Default to 0 if labels not found or matrix issue
        
    critical_error_rate = (critical_errors_count / total_predictions) * 100 if total_predictions > 0 else 0
    # --- End Critical Error Rate Calculation --- 

    summary_metrics = {
        'cohens_kappa': kappa, 
        'overall_accuracy': overall_accuracy,
        'workload_reduction': workload_reduction, 
        'discrepancy_rate': discrepancy_rate,
        'sensitivity_include': sensitivity_include, 
        'precision_include': precision_include,
        'f1_include': f1_include, 
        'specificity_for_include_task': specificity_for_include_task,
        'ai_maybe_rate': ai_maybe_rate, 
        'human_maybe_rate': human_maybe_rate,
        'critical_error_rate_ie': critical_error_rate, # ADDED
        'total_compared': total_predictions
    }
    return {
        'metrics': summary_metrics, 
        'matrix_3x3': cm_3x3_dict, # Pass the dict containing 'labels' and 'matrix_data'
        'class_metrics': class_metrics, 
        'maybe_resolution': maybe_resolution_metrics
    }


@app.route('/calculate_metrics', methods=['POST'])
def calculate_metrics_route():
    session_id = request.form.get('test_session_id')
    if not session_id or session_id not in test_sessions:
        flash('Test session not found.', 'error');
        return redirect(url_for('abstract_screening_page')) # CORRECTED
    session_data = test_sessions.get(session_id)
    if not session_data:
        flash('Test session data missing.', 'error');
        return redirect(url_for('abstract_screening_page')) # CORRECTED

    stored_test_items = session_data.get('test_items_data', [])
    ai_decisions_all, human_decisions_all, comparison_display_list = [], [], []
    valid_decision_labels = ['INCLUDE', 'EXCLUDE', 'MAYBE'] # Keep MAYBE for 3x3 calculation

    for item_data in stored_test_items:
        item_id = item_data['id']
        decision_key = f'decision-{item_id}'
        if decision_key in request.form:
            human_decision = request.form[decision_key]
            ai_decision = item_data['ai_decision']
            # Ensure only valid labels are used for metric calculation
            if ai_decision in valid_decision_labels and human_decision in valid_decision_labels:
                ai_decisions_all.append(ai_decision)
                human_decisions_all.append(human_decision)
            # Still add to comparison list even if decisions are not I/M/E (e.g., API_ERROR)
            comparison_display_list.append({
                'title': item_data['title'], 
                'ai_decision': ai_decision, 
                'ai_reasoning': item_data['ai_reasoning'], 
                'human_decision': human_decision,
                'match': ai_decision == human_decision if ai_decision in valid_decision_labels and human_decision in valid_decision_labels else False
            })

    if not ai_decisions_all or not human_decisions_all: # This check is crucial
        flash('No valid decisions (I/M/E) for comparison. Ensure you selected human decisions for some items.', 'warning') # Updated flash message
        # Pass necessary variables even if empty, or metrics_results.html might break
        default_empty_matrix = {
            'labels': valid_decision_labels, 
            # Use 'matrix_data' key here as well
            'matrix_data': [[0]*len(valid_decision_labels) for _ in range(len(valid_decision_labels))]
        }
        # Provide default empty structures for other potentially accessed dicts
        default_metrics = { # Ensure all keys accessed in template exist
            'overall_accuracy': 0, 'cohens_kappa': 0, 'discrepancy_rate': 0, 
            'sensitivity_include': 0, 'precision_include': 0, 'f1_include': 0,
            'specificity_for_include_task': 0, 'workload_reduction': 0,
            'ai_maybe_rate': 0, 'human_maybe_rate': 0, 'total_compared': 0
        }
        default_class_metrics = {label: {'precision': 0, 'recall': 0, 'f1_score': 0, 'tp':0, 'fp':0, 'fn':0, 'specificity': 0} for label in valid_decision_labels}
        default_maybe_res = {
             'ai_maybe_to_human_include': 0, 'ai_maybe_to_human_exclude': 0, 'ai_maybe_to_human_maybe': 0,
             'human_maybe_to_ai_include': 0, 'human_maybe_to_ai_exclude': 0
        }

        return render_template('metrics_results.html', 
                               metrics=default_metrics, 
                               matrix_3x3=default_empty_matrix, # Use the corrected structure
                               class_metrics=default_class_metrics, 
                               maybe_resolution=default_maybe_res,
                               comparison=comparison_display_list, 
                               total_samples=0,
                               session_id=session_id, 
                               labels_order=valid_decision_labels,
                               current_year=datetime.datetime.now().year) # ADDED current_year

    # If we have data, calculate metrics
    results_data = calculate_performance_metrics(ai_decisions_all, human_decisions_all, labels_order=valid_decision_labels)
    if session_id in test_sessions: # Ensure session still exists
      test_sessions[session_id]['full_metrics_results'] = results_data # Store full results in session

    # Unpack results_data for clarity in render_template, or pass as **results_data
    return render_template(
        'metrics_results.html',
        metrics=results_data['metrics'],
        matrix_3x3=results_data['matrix_3x3'], # This now contains 'matrix_data' key
        class_metrics=results_data['class_metrics'],
        maybe_resolution=results_data['maybe_resolution'],
        comparison=comparison_display_list,
        total_samples=results_data['metrics'].get('total_compared', 0),
        session_id=session_id,
        labels_order=valid_decision_labels, # Using the locally defined valid_decision_labels
        current_year=datetime.datetime.now().year # ADDED current_year
    )


# --- SSE Progress Streaming Route ---
def generate_progress_events(total_items, items_iterator_func):
    processed_count = 0
    yield f"data: {json.dumps({'type': 'start', 'total': total_items})}\n\n"
    try:
        for item_index, screening_output in items_iterator_func():  # Expecting item_index and the full screening_output dict
            processed_count += 1
            progress_percentage = int((processed_count / total_items) * 100)
            progress_data = {
                'type': 'progress', 'count': processed_count, 'total': total_items,
                'percentage': progress_percentage,
                'current_item_title': screening_output.get('title', 'Processing...'),
                'decision': screening_output.get('decision', '')
            }
            yield f"data: {json.dumps(progress_data)}\n\n"
            time.sleep(0.02)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Error during item processing: {str(e)}'})}\n\n"
        traceback.print_exc()
        return

    yield f"data: {json.dumps({'type': 'complete', 'message': 'Screening finished.'})}\n\n"


@app.route('/stream_screen_file', methods=['POST'])
def stream_screen_file():
    if 'file' not in request.files: return Response(f"data: {json.dumps({'type': 'error', 'message': 'No file part.'})}\n\n", mimetype='text/event-stream')
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename): return Response(f"data: {json.dumps({'type': 'error', 'message': 'No selected/invalid file.'})}\n\n", mimetype='text/event-stream')

    # --- NEW: Get filter inputs from form ---
    line_range_input = request.form.get('line_range_filter', '').strip()
    title_filter_input = request.form.get('title_text_filter', '').strip()
    # --- END NEW ---

    try:
        df = load_literature_ris(file.stream)
        if df is None or df.empty: return Response(f"data: {json.dumps({'type': 'error', 'message': 'Failed to load RIS or file empty.'})}\n\n", mimetype='text/event-stream')
        
        # Ensure essential columns exist, and fill if not
        if 'abstract' not in df.columns: return Response(f"data: {json.dumps({'type': 'error', 'message': 'RIS missing abstract.'})}\n\n", mimetype='text/event-stream')
        if 'title' not in df.columns: df['title'] = pd.Series(["Title Not Found"] * len(df))
        else: df['title'] = df['title'].fillna("Title Not Found")
        if 'authors' not in df.columns: df['authors'] = pd.Series([[] for _ in range(len(df))])
        else: df['authors'] = df['authors'].apply(lambda x: x if isinstance(x, list) else [])

        # --- NEW: Apply filters ---
        df_for_screening = df.copy()  # Operate on a copy
        original_df_count = len(df)
        filter_description = "all entries"

        if title_filter_input:
            df_for_screening = df_for_screening[
                df_for_screening['title'].str.contains(title_filter_input, case=False, na=False)]
            filter_description = f"entries matching title '{title_filter_input}'"
            if df_for_screening.empty:
                message = f'No articles found matching title: "{title_filter_input}"'
                return Response(
                    f"data: {json.dumps({'type': 'error', 'message': message})}\n\n",
                    mimetype='text/event-stream'
                )

        elif line_range_input:
            try:
                start_idx, end_idx = parse_line_range(line_range_input, original_df_count)
                if start_idx >= end_idx:
                    message = f'The range "{line_range_input}" is invalid or results in no articles.'
                    return Response(
                        f"data: {json.dumps({'type': 'error', 'message': message})}\n\n",
                        mimetype='text/event-stream'
                    )
                df_for_screening = df_for_screening.iloc[start_idx:end_idx]
                filter_description = f"entries in 1-based range [{start_idx + 1}-{end_idx}]"
                if df_for_screening.empty:
                    message = f'The range "{line_range_input}" resulted in no articles to screen.'
                    return Response(
                        f"data: {json.dumps({'type': 'error', 'message': message})}\n\n",
                        mimetype='text/event-stream'
                    )
            except ValueError as e:
                message = f'Invalid range format for "{line_range_input}": {str(e)}'
                return Response(
                    f"data: {json.dumps({'type': 'error', 'message': message})}\n\n",
                    mimetype='text/event-stream'
                )

        total_entries_to_screen = len(df_for_screening)
        if total_entries_to_screen == 0:
            return Response(
                f"data: {json.dumps({'type': 'error', 'message': 'No articles to screen (file might be empty or filters resulted in no matches).'})}\n\n",
                mimetype='text/event-stream'
            )
        # --- END NEW ---

        criteria_prompt_text = get_screening_criteria()
        # total_entries = len(df) # OLD, using total_entries_to_screen now
        current_llm_config_data = get_current_llm_config(session)
        provider_name = current_llm_config_data['provider_name']
        model_id = current_llm_config_data['model_id']
        base_url = get_base_url_for_provider(provider_name)
        provider_info = get_llm_providers_info().get(provider_name, {})
        # Corrected access to api_key_session_key based on actual structure from config.py
        session_key_name = provider_info.get("api_key_session_key") 
        api_key = session.get(session_key_name) if session_key_name else None

        if not api_key:
            error_message = f"API Key for {provider_name} must be provided via the configuration form for this session."
            return Response(f"data: {json.dumps({'type': 'error', 'message': error_message, 'needs_config': True})}\n\n", mimetype='text/event-stream')

        screening_id = str(uuid.uuid4())
        original_filename = file.filename

        # --- Refactored generator for Full Screening SSE --- 
        # MODIFIED: Pass df_for_screening and total_entries_to_screen to the generator
        def generate_full_screening_progress(df_to_process, num_total_items, current_filter_desc):
            processed_count = 0
            # SSE 'start' event with the count of items TO BE SCREENED
            yield f"data: {json.dumps({'type': 'start', 'total': num_total_items, 'filter_info': current_filter_desc})}\n\n"
            temp_results_list = []
            futures_map = {}

            with ThreadPoolExecutor(max_workers=8) as executor:
                # Iterate over the (potentially filtered) DataFrame
                for index, row in df_to_process.iterrows(): # MODIFIED: use df_to_process
                    abstract = row.get('abstract')
                    future = executor.submit(
                        _perform_screening_on_abstract,
                        abstract, criteria_prompt_text,
                        provider_name, model_id, api_key, base_url
                    )
                    futures_map[future] = {'index': index, 'row': row}

                # Process futures as they complete
                for future in as_completed(futures_map):
                    original_data = futures_map[future]
                    index = original_data['index']
                    row = original_data['row']
                    title = row.get('title', "N/A")
                    authors_list = row.get('authors', [])
                    authors_str = ", ".join(authors_list) if authors_list else "Authors Not Found"

                    try:
                        screening_result = future.result()
                        if screening_result['decision'] == "CONFIG_ERROR":
                            raise Exception(f"CONFIG_ERROR from worker: {screening_result['reasoning']}")

                        processed_count += 1
                        progress_percentage = int((processed_count / num_total_items) * 100) if num_total_items > 0 else 0
                        output_data = {
                            'index': index + 1, 'title': title, 'authors': authors_str,
                            'decision': screening_result['decision'], 'reasoning': screening_result['reasoning']
                        }
                        temp_results_list.append(output_data)
                        progress_event = {
                            'type': 'progress', 'count': processed_count, 'total': num_total_items,
                            'percentage': progress_percentage, 'current_item_title': title,
                            'decision': screening_result['decision']
                        }
                        yield f"data: {json.dumps(progress_event)}\n\n"

                    except Exception as e:
                        processed_count += 1 # Still increment for progress tracking
                        progress_percentage = int((processed_count / num_total_items) * 100) if num_total_items > 0 else 0
                        error_message_item = f"Error processing item '{title[:30]}...': {e}"
                        app_logger.error(f"Error processing item (original index {index}): {e}")
                        traceback.print_exc()
                        # Send progress event even for error, but with an error decision
                        progress_event = {
                            'type': 'progress', 'count': processed_count, 'total': num_total_items,
                            'percentage': progress_percentage, 'current_item_title': title,
                            'decision': 'ITEM_ERROR' # Specific marker for item processing error
                        }
                        yield f"data: {json.dumps(progress_event)}\n\n"
                        # Optionally, add a placeholder to temp_results_list for this error
                        temp_results_list.append({
                            'index': index + 1, 'title': title, 'authors': authors_str,
                            'decision': 'ITEM_ERROR', 'reasoning': str(e)
                        })

            # After loop, store results in global dict
            temp_results_list.sort(key=lambda x: x.get('index', float('inf')))
            full_screening_sessions[screening_id] = {
                'filename': original_filename, 
                'results': temp_results_list,
                'filter_applied': current_filter_desc # Store filter info with results
            }
            
            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Screening finished.', 'screening_id': screening_id})}\n\n"

        # Return the Response using the new generator    
        # MODIFIED: Pass df_for_screening, total_entries_to_screen, and filter_description
        return Response(generate_full_screening_progress(df_for_screening, total_entries_to_screen, filter_description), mimetype='text/event-stream')
    
    except Exception as e:
        app_logger.exception("Server error before full streaming")
        return Response(f"data: {json.dumps({'type': 'error', 'message': f'Server error before full streaming: {str(e)}'})}\n\n", mimetype='text/event-stream')


@app.route('/show_screening_results/<screening_id>', endpoint='show_screening_results') 
def show_screening_results(screening_id):
    session_data = full_screening_sessions.get(screening_id)
    
    if not session_data:
        flash("Screening results not found or may have expired.", "warning")
        return redirect(url_for('abstract_screening_page')) 
        
    results = session_data.get('results', [])
    filename = session_data.get('filename', 'Screened File')
    current_year = datetime.datetime.now().year
    
    return render_template('results.html', 
                           results=results, 
                           filename=filename,
                           screening_id=screening_id, 
                           current_year=current_year,
                           filter_applied=session_data.get('filter_applied', 'all entries') # Pass filter info to results page
                          )


# --- New Test Screening SSE Route ---
@app.route('/stream_test_screen_file', methods=['POST'], endpoint='stream_test_screen_file')
def stream_test_screen_file():
    if 'file' not in request.files:
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'No file part.'})}\n\n", mimetype='text/event-stream')

    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'No selected/invalid file.'})}\n\n", mimetype='text/event-stream')

    # --- Get ALL form fields first, ensuring they are defined before the main try block ---
    try:
        sample_size_str = request.form.get('sample_size', '10') 
        sample_size = int(sample_size_str)
        sample_size = max(5, min(9999, sample_size)) 
    except ValueError: 
        sample_size = 10 # Default if conversion fails
    
    # These must be defined at this level to be accessible in the subsequent try block's main logic
    line_range_input = request.form.get('line_range_filter', '').strip()
    title_filter_input = request.form.get('title_text_filter', '').strip()
    # --- Form fields are now defined ---
    
    try: 
        df = load_literature_ris(file.stream)
        if df is None or df.empty:
            return Response(f"data: {json.dumps({'type': 'error', 'message': 'Failed to load RIS or file empty.'})}\n\n", mimetype='text/event-stream')
        if 'abstract' not in df.columns:
            return Response(f"data: {json.dumps({'type': 'error', 'message': 'RIS missing abstract column.'})}\n\n", mimetype='text/event-stream')
        df['title'] = df.get('title', pd.Series(["Title Not Found"] * len(df))).fillna("Title Not Found")
        df['authors'] = df.get('authors', pd.Series([[] for _ in range(len(df))]))
        df['authors'] = df['authors'].apply(lambda x: x if isinstance(x, list) else [])

        # --- NEW: Apply filters before sampling for Test Screening ---
        df_for_sampling = df.copy()
        original_df_count = len(df)
        filter_description = "all entries"

        if title_filter_input: # This is where the NameError previously occurred
            df_for_sampling = df_for_sampling[df_for_sampling['title'].str.contains(title_filter_input, case=False, na=False)]
            filter_description = f"entries matching title '{title_filter_input}'"
            if df_for_sampling.empty:
                msg = f'No articles found matching title: "{title_filter_input}" to sample from.'
                return Response(f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n", mimetype='text/event-stream')
        
        elif line_range_input:
            try:
                start_idx, end_idx = parse_line_range(line_range_input, original_df_count)
                if start_idx >= end_idx:
                    msg = f'The range "{line_range_input}" is invalid or results in no articles to sample from.'
                    return Response(f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n", mimetype='text/event-stream')
                df_for_sampling = df_for_sampling.iloc[start_idx:end_idx]
                filter_description = f"entries in 1-based range [{start_idx + 1}-{end_idx}]"
                if df_for_sampling.empty:
                    msg = f'The range "{line_range_input}" resulted in no articles to sample from.'
                    return Response(f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n", mimetype='text/event-stream')
            except ValueError as e:
                msg = f'Invalid range format for "{line_range_input}": {str(e)}'
                return Response(f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n", mimetype='text/event-stream')
        
        if df_for_sampling.empty:
             return Response(f"data: {json.dumps({'type': 'error', 'message': 'No articles found after applying filters to sample from.'})}\n\n", mimetype='text/event-stream')

        sample_df = df_for_sampling.head(min(sample_size, len(df_for_sampling)))
        actual_sample_size = len(sample_df)
        # --- END NEW ---

        if actual_sample_size == 0:
             return Response(f"data: {json.dumps({'type': 'error', 'message': 'No entries found in the file to sample (after filters if any).'})}\n\n", mimetype='text/event-stream')

        criteria_prompt_text = get_screening_criteria()
        current_llm_config_data = get_current_llm_config(session)
        provider_name = current_llm_config_data['provider_name']
        model_id = current_llm_config_data['model_id']
        base_url = get_base_url_for_provider(provider_name)
        
        provider_info = get_llm_providers_info().get(provider_name, {})
        session_key_name = provider_info.get("api_key_session_key")
        api_key = session.get(session_key_name) if session_key_name else None

        if not api_key:
            error_message = f"API Key for {provider_name} must be provided via the configuration form for this session."
            return Response(f"data: {json.dumps({'type': 'error', 'message': error_message, 'needs_config': True})}\n\n", mimetype='text/event-stream')

        session_id = str(uuid.uuid4())
        test_sessions[session_id] = {
             'file_name': file.filename,
             'sample_size': actual_sample_size, 
             'test_items_data': [],
             'filter_applied': filter_description 
         }

        def generate_test_progress(current_sample_df, num_actual_sample_items, current_filter_desc):
            processed_count = 0
            yield f"data: {json.dumps({'type': 'start', 'total': num_actual_sample_items, 'filter_info': current_filter_desc})}\n\n"
            temp_results_list = []
            futures_map = {}
            
            with ThreadPoolExecutor(max_workers=8) as executor:
                for index, row in current_sample_df.iterrows(): 
                    abstract = row.get('abstract')
                    future = executor.submit(
                        _perform_screening_on_abstract,
                        abstract, criteria_prompt_text,
                        provider_name, model_id, api_key, base_url
                    )
                    futures_map[future] = {'index': index, 'row': row}

                for future in as_completed(futures_map):
                    original_data = futures_map[future]
                    index = original_data['index']
                    row = original_data['row']
                    title = row.get('title', "N/A")
                    abstract_text = row.get('abstract')
                    authors_list = row.get('authors', [])
                    authors_str = ", ".join(authors_list) if authors_list else "Authors Not Found"

                    try:
                        screening_result = future.result()
                        if screening_result['decision'] == "CONFIG_ERROR":
                            raise Exception(f"CONFIG_ERROR from worker: {screening_result['reasoning']}")

                        processed_count += 1
                        progress_percentage = int((processed_count / num_actual_sample_items) * 100) if num_actual_sample_items > 0 else 0
                        item_id = str(uuid.uuid4())
                        test_item_template_data = {
                            'id': item_id, 'original_index': index, 'title': title,
                            'authors': authors_str, 'abstract': abstract_text,
                            'ai_decision': screening_result['decision'], 'ai_reasoning': screening_result['reasoning']
                        }
                        temp_results_list.append(test_item_template_data)
                        progress_data = {
                            'type': 'progress', 'count': processed_count, 'total': num_actual_sample_items,
                            'percentage': progress_percentage, 'current_item_title': title,
                            'decision': screening_result['decision']
                        }
                        yield f"data: {json.dumps(progress_data)}\n\n"

                    except Exception as e:
                        processed_count += 1
                        progress_percentage = int((processed_count / num_actual_sample_items) * 100) if num_actual_sample_items > 0 else 0
                        error_message_item = f"Error processing item '{title[:30]}...': {e}"
                        app_logger.error(f"Error processing item (original index {index}): {e}")
                        traceback.print_exc()
                        progress_data = {
                             'type': 'progress', 'count': processed_count, 'total': num_actual_sample_items,
                             'percentage': progress_percentage, 'current_item_title': title,
                             'decision': 'ITEM_ERROR' 
                         }
                        yield f"data: {json.dumps(progress_data)}\n\n"
                        temp_results_list.append({
                            'id': str(uuid.uuid4()), 'original_index': index, 'title': title,
                            'authors': authors_str, 'abstract': abstract_text,
                            'ai_decision': 'ITEM_ERROR', 'ai_reasoning': str(e)
                        })
            
            temp_results_list.sort(key=lambda x: x.get('original_index', float('inf')))
            if session_id in test_sessions:
                 test_sessions[session_id]['test_items_data'] = temp_results_list
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Test screening finished.', 'session_id': session_id})}\n\n"

        return Response(generate_test_progress(sample_df, actual_sample_size, filter_description), mimetype='text/event-stream')

    except Exception as e: 
        app_logger.exception("Server error during test streaming processing")
        return Response(f"data: {json.dumps({'type': 'error', 'message': f'Server error during test streaming processing: {str(e)}'})}\n\n", mimetype='text/event-stream')


# --- New Route to Show Test Results ---
@app.route('/show_test_results/<session_id>', endpoint='show_test_results')
def show_test_results(session_id):
    if not session_id or session_id not in test_sessions:
        flash('Test session not found or expired. Please start a new test.', 'error')
        return redirect(url_for('abstract_screening_page'))

    session_data = test_sessions.get(session_id)
    test_items = session_data.get('test_items_data')

    if not test_items: # If empty list or key missing
         flash('No test items found in session for display.', 'warning')
         return redirect(url_for('abstract_screening_page'))

    current_year = datetime.datetime.now().year
    return render_template('test_results.html',
                           test_items=test_items,
                           session_id=session_id,
                           current_year=current_year,
                           # --- ADDED: Pass filter_applied to test_results.html ---
                           filter_applied=session_data.get('filter_applied', 'all entries'))


# --- New Download Route --- 
@app.route('/download_results/<screening_id>/<format>', endpoint='download_results')
def download_results(screening_id, format):
    session_data = full_screening_sessions.get(screening_id)
    
    if not session_data:
        flash("Could not find screening results data to download (it might have expired or been viewed already without download).", "error")
        return redirect(request.referrer or url_for('abstract_screening_page')) 
        
    results_list = session_data.get('results', [])
    filename_base = session_data.get('filename', 'screening_results')
    # Clean filename slightly
    filename_base = filename_base.replace('.ris', '').replace('.txt', '')
    
    if not results_list:
         flash("No results found within the screening data to download.", "warning")
         return redirect(request.referrer or url_for('abstract_screening_page'))
         
    # Convert list of dicts to DataFrame for easier export
    try:
        df = pd.DataFrame(results_list)
        # Select/rename columns if desired for export
        # df_export = df[['index', 'title', 'authors', 'decision', 'reasoning']] 
    except Exception as e:
         flash(f"Error converting results to DataFrame: {e}", "error")
         return redirect(request.referrer or url_for('abstract_screening_page'))

    # Prepare file in memory
    output_buffer = None
    mimetype = None
    download_filename = None

    try:
        if format == 'csv':
            output_buffer = io.StringIO()
            df.to_csv(output_buffer, index=False, encoding='utf-8-sig')
            mimetype = 'text/csv'
            download_filename = f"{filename_base}_results.csv"
            output_buffer.seek(0)
            # For CSV from StringIO, we need BytesIO wrapper for send_file
            bytes_buffer = io.BytesIO(output_buffer.getvalue().encode('utf-8-sig'))
            bytes_buffer.seek(0)
            output_buffer = bytes_buffer # Use the BytesIO buffer
            
        elif format == 'xlsx':
            output_buffer = io.BytesIO()
            with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Screening Results')
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            download_filename = f"{filename_base}_results.xlsx"
            output_buffer.seek(0)
            
        elif format == 'json':
            output_buffer = io.StringIO()
            df.to_json(output_buffer, orient='records', indent=4)
            mimetype = 'application/json'
            download_filename = f"{filename_base}_results.json"
            output_buffer.seek(0)
             # For JSON from StringIO, we need BytesIO wrapper for send_file
            bytes_buffer = io.BytesIO(output_buffer.getvalue().encode('utf-8'))
            bytes_buffer.seek(0)
            output_buffer = bytes_buffer # Use the BytesIO buffer
        else:
            flash(f"Unsupported download format: {format}", "error")
            return redirect(request.referrer or url_for('abstract_screening_page'))

        # Clean up the data from the global dictionary after preparing download
        # We poped it in show_screening_results, so it should be gone here anyway
        # full_screening_sessions.pop(screening_id, None) 
            
        return send_file(
            output_buffer,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_filename
        )

    except Exception as e:
        flash(f"Error generating download file ({format}): {e}", "error")
        traceback.print_exc()
        return redirect(request.referrer or url_for('abstract_screening_page'))


# --- Full-Text PDF Screening Routes --- 

@app.route('/screen_pdf_decision', methods=['POST'], endpoint='screen_pdf_decision')
def screen_pdf_decision():
    if 'pdf_file' not in request.files: flash('No PDF file part...', 'error'); return redirect(url_for('full_text_screening_page'))
    file = request.files['pdf_file']
    if file.filename == '': flash('No PDF file selected.', 'error'); return redirect(url_for('full_text_screening_page'))

    if file and file.filename.lower().endswith('.pdf'):
        original_filename = secure_filename(file.filename)
        pdf_screening_id = str(uuid.uuid4()) # Generate ID for this screening session
        
        # --- NEW: Save the uploaded PDF file --- 
        # Use pdf_screening_id to create a unique filename to avoid conflicts
        # And to easily associate the stored file with the screening session
        saved_pdf_filename = f"{pdf_screening_id}_{original_filename}"
        pdf_save_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_pdf_filename)
        
        try:
            file.save(pdf_save_path) # Save the uploaded file object
            app_logger.info(f"PDF saved to: {pdf_save_path}")

            # Now, process the saved file instead of the raw stream for consistency
            # Or, for efficiency, read the stream for processing and only use saved path for later serving.
            # For now, let's process the stream as before, and keep track of the saved path.
            # Reset stream pointer for reading after save (if stream is to be reused)
            file.stream.seek(0) 
            # --- END NEW ---

            # full_text = extract_text_from_pdf(file.stream) # OLD
            full_text = extract_text_from_pdf(file.stream, ocr_language='eng') # Pass stream, ensure language if needed
            
            if full_text is None: 
                flash(f"Could not extract text from PDF: {original_filename}.", "error")
                # Optionally, delete the saved PDF if extraction fails immediately
                # if os.path.exists(pdf_save_path): os.remove(pdf_save_path)
                return redirect(url_for('full_text_screening_page'))
            
            # Get criteria and LLM config
            criteria_full_text = get_screening_criteria()
            current_llm_config_data = get_current_llm_config(session)
            provider_name = current_llm_config_data['provider_name']
            model_id = current_llm_config_data['model_id']
            base_url = get_base_url_for_provider(provider_name)
            provider_info = get_llm_providers_info().get(provider_name, {})
            session_key_name = provider_info.get("api_key_session_key")
            api_key = session.get(session_key_name) if session_key_name else None

            if not api_key:
                flash(f"API Key for {provider_name} must be provided via the configuration form for this session.", "error")
                return redirect(url_for('llm_config_page'))
            
            # Construct prompt (using existing logic, but might need adjustment for "full text")
            # Maybe add a prefix to criteria or modify output instructions slightly? 
            # For now, use existing prompt structure but pass full_text as if it were abstract.
            # We might need a construct_fulltext_prompt later.
            prompt_data = construct_llm_prompt(full_text, criteria_full_text)
            if not prompt_data:
                flash("Failed to construct prompt...", "error")
                return redirect(url_for('full_text_screening_page'))

            # Call LLM (Synchronous)
            screening_result = call_llm_api(prompt_data, provider_name, model_id, api_key, base_url)
            
            pdf_screening_results[pdf_screening_id] = {
                'filename': original_filename, # Original filename for display
                'saved_pdf_path': pdf_save_path, # Store the path to the saved PDF
                'decision': screening_result.get('label', 'ERROR'),
                'reasoning': screening_result.get('justification', '-'),
                'extracted_text_preview': full_text[:2000] + ("... (truncated)" if len(full_text) > 2000 else "")
            }

            return redirect(url_for('show_pdf_result', pdf_screening_id=pdf_screening_id))

        except Exception as e:
            flash(f"An error occurred processing PDF {original_filename}: {e}", "error")
            app_logger.exception(f"An error occurred processing PDF {original_filename}") # replaces traceback.print_exc()
            return redirect(url_for('full_text_screening_page'))
    else:
        flash('Invalid file type. Please upload a PDF file.', 'error')
        return redirect(url_for('full_text_screening_page'))

@app.route('/show_pdf_result/<pdf_screening_id>', endpoint='show_pdf_result')
def show_pdf_result(pdf_screening_id):
    result_data = pdf_screening_results.get(pdf_screening_id) # Use .get() to keep the entry for PDF serving
    
    if not result_data:
        flash("PDF screening result not found. It might have expired or was not processed correctly.", "warning") # Adjusted message
        return redirect(url_for('full_text_screening_page'))
        
    current_year = datetime.datetime.now().year
    return render_template('pdf_result.html',
                           pdf_id=pdf_screening_id, # Pass the ID itself
                           filename=result_data.get('filename'),
                           decision=result_data.get('decision'),
                           reasoning=result_data.get('reasoning'),
                           extracted_text_preview=result_data.get('extracted_text_preview'),
                           current_year=current_year)


# --- ADDED: Data Extraction Routes ---
@app.route('/data_extraction', methods=['GET'], endpoint='data_extraction_page')
def data_extraction_page():
    current_year = datetime.datetime.now().year
    return render_template('data_extraction.html', current_year=current_year)

@app.route('/extract_data_pdf', methods=['POST'], endpoint='extract_data_pdf')
def extract_data_pdf():
    if 'pdf_extract_file' not in request.files:
        flash('No PDF file part in the request.', 'error')
        return redirect(url_for('data_extraction_page'))

    file = request.files['pdf_extract_file']
    if file.filename == '':
        flash('No PDF file selected.', 'error')
        return redirect(url_for('data_extraction_page'))

    if file and file.filename.lower().endswith('.pdf'):
        filename = secure_filename(file.filename)
        app_logger.info(f"Starting data extraction for PDF: {filename}")
        try:
            full_text = extract_text_from_pdf(file.stream)
            if full_text is None:
                flash(f"Could not extract text from PDF: {filename}.", "error")
                return redirect(url_for('data_extraction_page'))
            
            app_logger.info(f"Extracted {len(full_text)} characters. Preparing extraction prompt...")
            
            # --- Gather User-Defined Extraction Fields --- 
            extraction_fields = {}
            field_index = 0
            while True:
                field_name = request.form.get(f'field_name_{field_index}')
                instruction = request.form.get(f'instruction_{field_index}')
                example = request.form.get(f'example_{field_index}', '') # Example is optional
                if field_name and instruction: # Only process if name and instruction exist
                    # Basic validation/sanitization for field name (key)
                    field_key = re.sub(r'\W|\s+', '_', field_name).strip('_').lower()
                    if not field_key: field_key = f"field_{field_index}" # Fallback key
                    extraction_fields[field_key] = {"instruction": instruction, "example": example}
                    field_index += 1
                else:
                    break # Stop when fields are no longer found
            if not extraction_fields:
                flash("No valid data extraction fields were defined.", "error")
                return redirect(url_for('data_extraction_page'))

            # --- Build Dynamic Extraction Prompt --- 
            output_format_instruction = "Provide the extracted information in a JSON format where keys are the field names ({field_names}) and values are the extracted data. If data for a field is not found, use null or an empty string for its value. ONLY output the JSON object.".format(
                field_names=", ".join(extraction_fields.keys())
            )
            extraction_prompt = f"""You are an AI assistant specialized in extracting specific information from medical research papers.
Task: Extract the following data points from the provided text based on the instructions for each field. 
{output_format_instruction}

Fields to Extract (with instructions and examples):
"""
            for key, data in extraction_fields.items():
                extraction_prompt += f"- Field Name (JSON Key): '{key}'\n"
                extraction_prompt += f"  Instruction/Question: {data['instruction']}\n"
                if data['example']:
                    extraction_prompt += f"  Example Desired Output: '{data['example']}'\n"
            # Aggressively truncate input text (Adjust MAX_INPUT_CHARS as needed)
            MAX_INPUT_CHARS = 30000 
            truncated_text = full_text[:MAX_INPUT_CHARS]
            if len(full_text) > MAX_INPUT_CHARS: app_logger.warning(f"Warning: Truncated PDF text from {len(full_text)} to {MAX_INPUT_CHARS} chars.")
            extraction_prompt += f"\n--- Full Text (potentially truncated) ---\n{truncated_text}\n--- End of Text ---\n\nExtracted JSON data:"""

            # --- Get LLM Config --- 
            current_llm_config_data = get_current_llm_config(session)
            provider_name = current_llm_config_data['provider_name']
            model_id = current_llm_config_data['model_id']
            base_url = get_base_url_for_provider(provider_name)
            provider_info = get_llm_providers_info().get(provider_name, {})
            session_key_name = provider_info.get("api_key_session_key")
            api_key = session.get(session_key_name) if session_key_name else None
            if not api_key: flash(f"API Key for {provider_name} must be provided...", "error"); return redirect(url_for('llm_config_page'))

            # --- Call LLM for Raw Content --- 
            app_logger.info(f"Sending extraction prompt to {provider_name}...")
            llm_response_raw = call_llm_api_raw_content(
                 {
                    "system_prompt": "You are an AI assistant performing data extraction. Output ONLY the requested JSON object, enclosed in ```json ... ``` if possible.", 
                    "main_prompt": extraction_prompt
                 }, 
                 provider_name, model_id, api_key, base_url, 
                 max_tokens_override=1500 
             )
            
            # --- Parse JSON Response --- 
            extracted_data = None
            if llm_response_raw and isinstance(llm_response_raw, str):
                if llm_response_raw.startswith("API_ERROR:"):
                    extracted_data = {"error": llm_response_raw}
                else:
                    try:
                        json_block_match = re.search(r'```json\s*(\{.*?\})\s*```', llm_response_raw, re.DOTALL)
                        json_str_to_parse = None
                        if json_block_match:
                            json_str_to_parse = json_block_match.group(1)
                        else:
                            json_obj_match = re.search(r'\{\s*\".*?\":.*?\}', llm_response_raw, re.DOTALL)
                            if json_obj_match:
                                json_str_to_parse = json_obj_match.group()
                        
                        if json_str_to_parse:
                            extracted_data = json.loads(json_str_to_parse)
                            app_logger.info("Successfully parsed JSON from LLM output.")
                        else:
                            app_logger.warning("Could not find valid JSON structure in LLM output.")
                            extracted_data = {"error": "LLM did not return expected JSON structure.", "raw_output": llm_response_raw[:500]}
                    except json.JSONDecodeError:
                        app_logger.error(f"Failed to decode JSON from LLM output: {llm_response_raw}")
                        extracted_data = {"error": "LLM output was not valid JSON.", "raw_output": llm_response_raw[:500]}
                    except Exception as parse_err:
                        app_logger.error(f"Unexpected error parsing LLM output: {parse_err}")
                        extracted_data = {"error": f"Unexpected error parsing output: {parse_err}", "raw_output": llm_response_raw[:500]}
            else:
                app_logger.warning("LLM call returned no content or unexpected type.")
                extracted_data = {"error": "LLM call returned no content or failed."}

            current_year = datetime.datetime.now().year
            return render_template('extraction_result.html',
                                   filename=filename,
                                   extraction_data=extracted_data,
                                   current_year=current_year)

        except Exception as e:
            flash(f"An error occurred during data extraction for {original_filename if 'original_filename' in locals() else 'Unknown PDF'}: {e}", "error")
            app_logger.exception(f"An error occurred during data extraction for PDF")
            return redirect(url_for('data_extraction_page'))
    else:
        flash('Invalid file type. Please upload a PDF file.', 'error')
        return redirect(url_for('data_extraction_page'))


# --- ADDED: Route to serve saved PDF files for preview ---
@app.route('/serve_pdf/<pdf_id>/<original_filename>', methods=['GET'])
def serve_pdf_file(pdf_id: str, original_filename: str):
    # Construct the filename as it was saved
    # This assumes the filename format f"{pdf_id}_{original_filename}" used during saving
    # Ensure original_filename is sanitized if it comes directly from URL path in a real scenario,
    # but here it's mainly for constructing the known saved name.
    # For security, it's better if the actual filename on disk is ONLY the pdf_id.pdf 
    # or if we look up the full saved_pdf_path from a secure mapping (e.g. pdf_screening_results[pdf_id]['saved_pdf_path'])
    # However, to keep it simple for now based on previous save logic:
    
    # Let's refine this: it's better to fetch path from our stored results for security and accuracy.
    session_data = pdf_screening_results.get(pdf_id)
    if not session_data or 'saved_pdf_path' not in session_data:
        return "PDF record not found or path missing.", 404

    saved_path = session_data['saved_pdf_path']
    
    # Use send_from_directory for security. 
    # It needs directory and filename separately.
    directory = os.path.dirname(saved_path)
    filename = os.path.basename(saved_path)

    if not os.path.exists(saved_path):
         return "PDF file not found on server.", 404

    try:
        return send_file(saved_path, as_attachment=False) # as_attachment=False for inline display
    except Exception as e:
        app_logger.error(f"Error serving PDF {filename}: {e}")
        traceback.print_exc()
        return "Error serving PDF.", 500
# --- END ADDED PDF serving route ---


# --- NEW: Batch Full-Text PDF Screening SSE Route (Skeleton) ---
@app.route('/batch_screen_pdfs_stream', methods=['POST'], endpoint='batch_screen_pdfs_stream_placeholder')
def batch_screen_pdfs_stream():
    app_logger.info("Batch PDF Stream: Request received.")
    
    uploaded_files = request.files.getlist("batch_pdf_files")
    title_filter_input = request.form.get('batch_pdf_title_filter', '').strip()
    order_filter_input = request.form.get('batch_pdf_order_filter', '').strip()

    if not uploaded_files or all(f.filename == '' for f in uploaded_files):
        app_logger.warning("Batch PDF Stream: No files were uploaded or all files are empty.")
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'No PDF files uploaded or all files are empty.'})}\n\n", mimetype='text/event-stream')

    initial_manifest = []
    for idx, file_storage_object in enumerate(uploaded_files):
        if file_storage_object and file_storage_object.filename:
            original_filename = secure_filename(file_storage_object.filename)
            initial_manifest.append({
                'original_index': idx, 
                'original_filename': original_filename,
                'file_storage': file_storage_object, 
                'saved_path': None 
            })
    
    if not initial_manifest:
        app_logger.warning("Batch PDF Stream: No valid files found in upload.")
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'No valid PDF files found in upload.'})}\n\n", mimetype='text/event-stream')

    app_logger.info(f"Batch PDF Stream: Initially {len(initial_manifest)} files uploaded.")
    app_logger.info(f"Batch PDF Stream: Title filter: '{title_filter_input}', Order filter: '{order_filter_input}'")

    files_to_process_manifest = list(initial_manifest)
    filter_description = "all uploaded files"
    applied_title_filter = False

    if title_filter_input:
        files_to_process_manifest = [
            item for item in files_to_process_manifest 
            if title_filter_input.lower() in item['original_filename'].lower()
        ]
        filter_description = f"files matching filename '{title_filter_input}'"
        applied_title_filter = True
        if not files_to_process_manifest:
            app_logger.info(f"Batch PDF Stream: No files matched title filter '{title_filter_input}'.")
            message_text = f'No PDF files found matching filename filter: "{title_filter_input}"' # Corrected
            return Response(f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n", mimetype='text/event-stream')
            
    if not applied_title_filter and order_filter_input: 
        try:
            num_items_for_order_filter = len(files_to_process_manifest)
            start_idx_0_based, end_idx_0_based_exclusive = parse_line_range(order_filter_input, num_items_for_order_filter)
            
            if start_idx_0_based >= end_idx_0_based_exclusive:
                app_logger.info(f"Batch PDF Stream: Order filter range '{order_filter_input}' is invalid or results in no files.")
                message_text = f'The order filter range "{order_filter_input}" is invalid or results in no files.' # Corrected
                return Response(f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n", mimetype='text/event-stream')

            files_to_process_manifest = files_to_process_manifest[start_idx_0_based:end_idx_0_based_exclusive]
            filter_description = f"files by order range [{start_idx_0_based+1}-{end_idx_0_based_exclusive}]"
            
            if not files_to_process_manifest:
                app_logger.info(f"Batch PDF Stream: No files matched order filter '{order_filter_input}'.")
                message_text = 'No PDF files found for the specified order range.' # Corrected
                return Response(f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n", mimetype='text/event-stream')
        
        except ValueError as e:
            app_logger.warning(f"Batch PDF Stream: Invalid order filter format '{order_filter_input}': {e}")
            message_text = f'Invalid format for order filter "{order_filter_input}": {str(e)}' # Corrected
            return Response(f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n", mimetype='text/event-stream')

    total_files_to_process = len(files_to_process_manifest)
    if total_files_to_process == 0 and (title_filter_input or order_filter_input):
        app_logger.info("Batch PDF Stream: No files selected for processing after filters.")
        message_text = 'No PDF files selected for processing after applying filters.' # Corrected
        return Response(f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n", mimetype='text/event-stream')

    app_logger.info(f"Batch PDF Stream: {total_files_to_process} file(s) selected. Filter applied: {filter_description}")
    selected_filenames_log = [item['original_filename'] for item in files_to_process_manifest]
    app_logger.info(f"Batch PDF Stream: Selected files for processing: {selected_filenames_log}")

    # --- Get LLM and Criteria Config ONCE before starting threads ---
    try:
        criteria_prompt_text = get_screening_criteria()
        current_llm_config_data = get_current_llm_config(session)
        llm_provider_name = current_llm_config_data['provider_name']
        llm_model_id = current_llm_config_data['model_id']
        llm_base_url = get_base_url_for_provider(llm_provider_name)
        
        provider_info = get_llm_providers_info().get(llm_provider_name, {})
        session_key_name = provider_info.get("api_key_session_key")
        llm_api_key = session.get(session_key_name) if session_key_name else None

        if not llm_api_key:
            app_logger.error("Batch PDF Stream: API Key missing in session for the selected LLM provider.")
            # Send an error event and stop
            # This error needs to be sent via SSE if we reach here after initial connection.
            def sse_error_gen():
                message_text = f'API Key for {llm_provider_name} must be provided via configuration.'
                yield f"data: {json.dumps({'type': 'error', 'message': message_text, 'needs_config': True})}\n\n"
            return Response(sse_error_gen(), mimetype='text/event-stream')
    except Exception as e_config:
        app_logger.exception("Batch PDF Stream: Error fetching LLM/Criteria configuration.")
        def sse_config_error_gen():
            message_text = f'Error fetching LLM/Criteria configuration: {str(e_config)}'
            yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
        return Response(sse_config_error_gen(), mimetype='text/event-stream')
    # --- END Config Fetch ---

    upload_folder_path = app.config['UPLOAD_FOLDER']

    # --- Pre-save files that need processing to unique temp paths ---
    files_ready_for_threads = []
    for item_manifest in files_to_process_manifest:
        file_storage = item_manifest['file_storage']
        original_filename = item_manifest['original_filename']
        try:
            file_storage.seek(0) # Reset stream before saving
            temp_file_id = str(uuid.uuid4())
            # Save with a name that indicates it's a temporary file for this batch operation
            processing_filename = f"batch_processing_{temp_file_id}_{original_filename}"
            processing_file_path = os.path.join(upload_folder_path, processing_filename)
            file_storage.save(processing_file_path)
            app_logger.info(f"Batch PDF: Pre-saved '{original_filename}' to '{processing_file_path}' for thread processing.")
            files_ready_for_threads.append({
                'original_filename': original_filename,
                'processing_file_path': processing_file_path # Pass the path to the thread
            })
        except Exception as e_save:
            app_logger.error(f"Batch PDF: Failed to pre-save file '{original_filename}' for processing: {e_save}")
            # Optionally, send an immediate SSE error for this file or collect errors
            # For now, this file will be skipped by the threads if it's not in files_ready_for_threads
            pass # Or append an error marker to files_ready_for_threads to report it
    # --- End Pre-save ---

    if not files_ready_for_threads:
        app_logger.warning("Batch PDF Stream: No files were successfully pre-saved for processing.")
        def sse_presave_error_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to prepare any files for batch processing.'})}\n\n"
        return Response(sse_presave_error_gen(), mimetype='text/event-stream')

    # Update total_files_to_process to reflect only successfully pre-saved files
    total_files_to_process = len(files_ready_for_threads) 

    def generate_processing_progress():
        yield f"data: {json.dumps({'type': 'start', 'total_uploaded': len(initial_manifest), 'total_to_process': total_files_to_process, 'filter_info': filter_description})}\n\n"
        
        processed_files_results = []
        futures_map = {}

        with ThreadPoolExecutor(max_workers=4) as executor:
            for thread_item_manifest in files_ready_for_threads: # Iterate over pre-saved file manifests
                future = executor.submit(
                    _perform_batch_pdf_screening_for_file, 
                    thread_item_manifest, # This now contains 'processing_file_path'
                    criteria_prompt_text, 
                    llm_provider_name, 
                    llm_model_id, 
                    llm_api_key, 
                    llm_base_url
                    # upload_folder is no longer needed by the helper as it gets a full path
                )
                futures_map[future] = thread_item_manifest['original_filename'] # For logging upon completion/error

            processed_count = 0
            # ... (as_completed loop remains similar, but _perform_batch_pdf_screening_for_file now takes different manifest) ...
            for future in as_completed(futures_map):
                original_filename_for_log = futures_map[future]
                try:
                    screening_result = future.result() # This is the dict returned by our helper
                    processed_files_results.append(screening_result)
                    processed_count += 1
                    yield f"data: {json.dumps({                        'type': 'progress',                         'count': processed_count,                         'total_to_process': total_files_to_process,                        'percentage': int((processed_count / total_files_to_process) * 100),                        'current_file_name': screening_result.get('filename', original_filename_for_log),                        'decision': screening_result.get('decision', 'ERROR')                     })}\n\n"
                except Exception as e_future:
                    processed_count += 1 # Still count it as processed (with error)
                    app_logger.error(f"Batch PDF: Exception processing future for {original_filename_for_log}: {e_future}")
                    processed_files_results.append({
                        'filename': original_filename_for_log, 
                        'decision': 'WORKER_ERROR', 
                        'reasoning': str(e_future)
                    })
                    yield f"data: {json.dumps({                        'type': 'progress',                         'count': processed_count,                        'total_to_process': total_files_to_process,                        'percentage': int((processed_count / total_files_to_process) * 100),                        'current_file_name': original_filename_for_log,                        'decision': 'WORKER_ERROR'                     })}\n\n"

        batch_session_id = str(uuid.uuid4())
        if processed_files_results: 
            full_screening_sessions[batch_session_id] = { 
                'filename': f"Batch PDF Results ({len(processed_files_results)} of {total_files_to_process} processed)", 
                'filter_applied': filter_description,
                'results': processed_files_results,
                'is_batch_pdf_result': True 
            }
            app_logger.info(f"Batch PDF Stream: Stored {len(processed_files_results)} results under batch ID {batch_session_id}")
        else:
            app_logger.warning("Batch PDF Stream: No results were processed or collected.")

        yield f"data: {json.dumps({'type': 'complete', 'message': 'Batch PDF processing finished.', 'batch_session_id': batch_session_id if processed_files_results else None})}\n\n"
        app_logger.info(f"Batch PDF stream: Processing SSE finished. Batch ID: {batch_session_id if processed_files_results else 'N/A'}")

    return Response(generate_processing_progress(), mimetype='text/event-stream')


# --- NEW Helper for processing a single PDF in batch ---
def _perform_batch_pdf_screening_for_file(item_manifest_with_path, criteria_prompt_text, llm_provider_name, llm_model_id, llm_api_key, llm_base_url):
    original_filename = item_manifest_with_path['original_filename']
    processing_file_path = item_manifest_with_path['processing_file_path'] # This is the FULL path

    try:
        app_logger.info(f"Batch PDF Thread: Processing '{original_filename}' from path '{processing_file_path}'.")
        with open(processing_file_path, 'rb') as saved_file_stream:
            full_text = extract_text_from_pdf(saved_file_stream, ocr_language='eng') 
        
        if full_text is None:
            app_logger.error(f"Batch PDF Thread: Failed to extract text from '{original_filename}'.")
            return {'filename': original_filename, 'decision': 'TEXT_EXTRACT_ERROR', 'reasoning': 'Failed to extract text from PDF.'}
        
        prompt_data = construct_llm_prompt(full_text, criteria_prompt_text)
        if not prompt_data:
            app_logger.error(f"Batch PDF Thread: Failed to construct LLM prompt for '{original_filename}'.")
            return {'filename': original_filename, 'decision': 'PROMPT_ERROR', 'reasoning': 'Failed to construct LLM prompt.'}
        
        api_result = call_llm_api(prompt_data, llm_provider_name, llm_model_id, llm_api_key, llm_base_url)
        
        return {
            'filename': original_filename,
            'decision': api_result.get('label', 'API_ERROR'),
            'reasoning': api_result.get('justification', 'API call failed or returned invalid data.')
        }

    except Exception as e_process:
        app_logger.exception(f"Batch PDF Thread: Error processing file '{original_filename}': {e_process}")
        return {'filename': original_filename, 'decision': 'FILE_PROCESSING_ERROR', 'reasoning': str(e_process)}
    finally:
        if os.path.exists(processing_file_path):
            try:
                os.remove(processing_file_path)
                app_logger.info(f"Batch PDF Thread: Cleaned up temporary file '{processing_file_path}'.")
            except Exception as e_cleanup:
                app_logger.error(f"Batch PDF Thread: Error cleaning up temp file '{processing_file_path}': {e_cleanup}")

# --- END NEW Helper ---


# --- NEW: Route to show Batch PDF Screening Results (Skeleton) ---
@app.route('/show_batch_pdf_results/<batch_session_id>', methods=['GET'], endpoint='show_batch_pdf_results_placeholder')
def show_batch_pdf_results(batch_session_id):
    app_logger.info(f"Request to show batch PDF results for ID: {batch_session_id}")
    batch_data = full_screening_sessions.get(batch_session_id)

    if not batch_data or not batch_data.get('is_batch_pdf_result', False):
        app_logger.warning(f"Batch PDF results not found or invalid for ID: {batch_session_id}")
        flash("Batch PDF screening results not found or may have expired.", "warning")
        return redirect(url_for('full_text_screening_page'))
    
    app_logger.info(f"Rendering batch PDF results for {batch_session_id}. Contains {len(batch_data.get('results', []))} items.")
    # app_logger.debug(f"Batch data content: {batch_data}") # Can be very verbose

    return render_template('batch_pdf_results.html', 
                           batch_info=batch_data, 
                           batch_id=batch_session_id,
                           current_year=datetime.datetime.now().year)
    
    # # Placeholder response until template is created
    # return f"Placeholder for Batch PDF Results. Batch ID: {batch_session_id}. Results count: {len(batch_data.get('results', []))}" 
# --- END NEW Batch PDF Results Route ---


# --- Run App ---
if __name__ == '__main__':
    app_logger.info("Starting Flask app in debug mode...") # Example for __main__
    app.run(debug=True, host='0.0.0.0', port=5050)

#test