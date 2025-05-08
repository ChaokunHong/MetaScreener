import os
import pandas as pd
import time
import datetime  # Explicitly import datetime for current year
import uuid
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.metrics import confusion_matrix, cohen_kappa_score, f1_score, precision_score, recall_score, \
    multilabel_confusion_matrix
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from werkzeug.utils import secure_filename
import traceback
import json  # For SSE
import sys # For printing to stderr

# Import functions from our utils and config
from utils import load_literature_ris, construct_llm_prompt, call_llm_api
from config import (
    get_screening_criteria, set_user_criteria, reset_to_default_criteria,
    DEFAULT_EXAMPLE_CRITERIA, USER_CRITERIA,
    get_llm_providers_info, get_current_llm_config,
    get_api_key_for_provider, get_base_url_for_provider
)

app = Flask(__name__)
app.secret_key = os.urandom(24)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'ris'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
test_sessions = {} # For holding test screening data + results before metrics
full_screening_sessions = {} # ADDED: For holding full screening results temporarily
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_criteria_object():
    from config import USER_CRITERIA, DEFAULT_EXAMPLE_CRITERIA
    return USER_CRITERIA if USER_CRITERIA is not None else DEFAULT_EXAMPLE_CRITERIA


# --- Route for LLM Configuration ---
@app.route('/configure_llm', methods=['POST'])
def configure_llm():
    print("--- Entering configure_llm --- ", file=sys.stderr)
    selected_provider = request.form.get('llm_provider')
    selected_model_id = request.form.get('llm_model_id')
    print(f"Provider: {selected_provider}, Model: {selected_model_id}", file=sys.stderr)

    providers_info = get_llm_providers_info()
    if selected_provider not in providers_info:
        flash('Invalid LLM Provider selected.', 'error')
        return redirect(url_for('llm_config_page'))

    provider_config = providers_info[selected_provider]

    session['selected_llm_provider'] = selected_provider
    session['selected_llm_model_id'] = selected_model_id

    api_key_form_field = f"{selected_provider.lower()}_api_key"
    user_api_key = request.form.get(api_key_form_field)
    print(f"Form field for key: '{api_key_form_field}'", file=sys.stderr)
    print(f"Submitted key value: '{user_api_key}' (Type: {type(user_api_key)})", file=sys.stderr)

    if user_api_key:
        print("User API key is truthy, attempting to save...", file=sys.stderr)
        session_key_for_api = provider_config.get("api_key_session_key")
        print(f"Session key name from config: '{session_key_for_api}'", file=sys.stderr)
        if session_key_for_api:
            session[session_key_for_api] = user_api_key
            print(f"Saved '{user_api_key[:5]}...' to session['{session_key_for_api}']", file=sys.stderr)
            flash(f'API Key for {selected_provider} updated in session.', 'info')
        else:
             print("ERROR: Could not find api_key_session_key in provider config!", file=sys.stderr)
    else:
        print("User API key is FALSY (empty or None), NOT saving to session.", file=sys.stderr)
        # Check if maybe clear was intended (less likely if user typed something)
        if not user_api_key and request.form.get(f'clear_{api_key_form_field}'):
             session_key_for_api = provider_config.get("api_key_session_key")
             if session_key_for_api and session_key_for_api in session:
                 session.pop(session_key_for_api)
                 print(f"Cleared key for {selected_provider} from session.", file=sys.stderr)
                 flash(f'API Key for {selected_provider} cleared from session.', 'info')

    print(f"Session contents after configure_llm: {session}", file=sys.stderr)
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
    # This page will need criteria and current_year
    criteria = get_current_criteria_object()
    current_year = datetime.datetime.now().year
    return render_template('screening_criteria.html', 
                           criteria=criteria, 
                           current_year=current_year)

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
        criteria_dict = {
            'population_criteria': request.form.get('population_criteria', ''),
            'intervention_criteria': request.form.get('intervention_criteria', ''),
            'comparison_criteria': request.form.get('comparison_criteria', ''),
            'outcome_criteria': request.form.get('outcome_criteria', ''),
            'time_criteria': request.form.get('time_criteria', ''),
            'other_inclusion_criteria': request.form.get('other_inclusion_criteria', ''),
            'exclusion_criteria': request.form.get('exclusion_criteria', '')
        }
        set_user_criteria(criteria_dict)
        flash('Screening criteria successfully saved!', 'success')
    except Exception as e:
        flash(f'Error saving screening criteria: {e}', 'error')
    return redirect(url_for('screening_criteria_page')) # MODIFIED REDIRECT


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
    return redirect(url_for('screening_actions_page'))
    # Option 2: Keep it as a non-SSE fallback (less ideal now)
    # Option 3: Remove it entirely if the button is gone / SSE is stable


@app.route('/screen_full_dataset/<session_id>')
def screen_full_dataset(session_id):
    if not session_id or session_id not in test_sessions: flash('Test session not found or expired.', 'error'); return redirect(url_for('screening_actions_page'))
    session_data = test_sessions.get(session_id)
    if not session_data: flash('Test session data missing.', 'error'); return redirect(url_for('screening_actions_page'))
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
                     print(f"Error processing item (index {index}) in sync route: {exc}")
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
        traceback.print_exc()
        flash(f"Error during full screening: {e}.", 'error')
        if session_id in test_sessions:
            del test_sessions[session_id]
        return redirect(url_for('screening_actions_page'))


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

    summary_metrics = {
        'cohens_kappa': kappa, # Pass the original kappa value
        'overall_accuracy': overall_accuracy,
        'workload_reduction': workload_reduction, 
        'discrepancy_rate': discrepancy_rate,
        'sensitivity_include': sensitivity_include, 
        'precision_include': precision_include,
        'f1_include': f1_include, 
        'specificity_for_include_task': specificity_for_include_task,
        'ai_maybe_rate': ai_maybe_rate, 
        'human_maybe_rate': human_maybe_rate,
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
        return redirect(url_for('screening_actions_page')) # MODIFIED REDIRECT (or a specific results page if one exists beyond test_results)
    session_data = test_sessions.get(session_id)
    if not session_data:
        flash('Test session data missing.', 'error');
        return redirect(url_for('screening_actions_page')) # MODIFIED REDIRECT

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

    try:
        df = load_literature_ris(file.stream)
        if df is None or df.empty: return Response(f"data: {json.dumps({'type': 'error', 'message': 'Failed to load RIS or file empty.'})}\n\n", mimetype='text/event-stream')
        if 'abstract' not in df.columns: return Response(f"data: {json.dumps({'type': 'error', 'message': 'RIS missing abstract.'})}\n\n", mimetype='text/event-stream')
        if 'title' not in df.columns: df['title'] = pd.Series(["Title Not Found"] * len(df))
        else: df['title'] = df['title'].fillna("Title Not Found")
        if 'authors' not in df.columns: df['authors'] = pd.Series([[] for _ in range(len(df))])
        else: df['authors'] = df['authors'].apply(lambda x: x if isinstance(x, list) else [])

        criteria_prompt_text = get_screening_criteria()
        total_entries = len(df)
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

        screening_id = str(uuid.uuid4())
        original_filename = file.filename

        # --- Refactored generator for Full Screening SSE --- 
        def generate_full_screening_progress():
            processed_count = 0
            yield f"data: {json.dumps({'type': 'start', 'total': total_entries})}\n\n"
            temp_results_list = []
            futures_map = {}

            with ThreadPoolExecutor(max_workers=8) as executor:
                # Submit all tasks
                for index, row in df.iterrows():
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
                        progress_percentage = int((processed_count / total_entries) * 100)
                        output_data = {
                            'index': index + 1, 'title': title, 'authors': authors_str,
                            'decision': screening_result['decision'], 'reasoning': screening_result['reasoning']
                        }
                        temp_results_list.append(output_data)
                        progress_event = {
                            'type': 'progress', 'count': processed_count, 'total': total_entries,
                            'percentage': progress_percentage, 'current_item_title': title,
                            'decision': screening_result['decision']
                        }
                        yield f"data: {json.dumps(progress_event)}\n\n"

                    except Exception as e:
                        processed_count += 1
                        progress_percentage = int((processed_count / total_entries) * 100)
                        error_message = f"Error processing item '{title[:30]}...': {e}"
                        print(f"Error processing item (index {index}): {e}")
                        traceback.print_exc()
                        progress_event = {
                            'type': 'progress', 'count': processed_count, 'total': total_entries,
                            'percentage': progress_percentage, 'current_item_title': title,
                            'decision': 'THREAD_ERROR'
                        }
                        yield f"data: {json.dumps(progress_event)}\n\n"

            # After loop, store results in global dict
            temp_results_list.sort(key=lambda x: x.get('index', float('inf'))) # Sort by index (row.name + 1)
            full_screening_sessions[screening_id] = {
                'filename': original_filename, 
                'results': temp_results_list
            }
            
            # Send completion event
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Screening finished.', 'screening_id': screening_id})}\n\n"

        # Return the Response using the new generator    
        return Response(generate_full_screening_progress(), mimetype='text/event-stream')
    
    except Exception as e:
        traceback.print_exc()
        return Response(f"data: {json.dumps({'type': 'error', 'message': f'Server error before full streaming: {str(e)}'})}\n\n", mimetype='text/event-stream')


@app.route('/show_screening_results/<screening_id>', endpoint='show_screening_results') 
def show_screening_results(screening_id):
    # Retrieve results from global dict using pop (removes after retrieval)
    session_data = full_screening_sessions.pop(screening_id, None)
    
    if not session_data:
        flash("Screening results not found or already viewed.", "warning")
        return redirect(url_for('screening_actions_page')) 
        
    results = session_data.get('results', [])
    filename = session_data.get('filename', 'Screened File')
    
    # The current_year needed by base.html should be added
    current_year = datetime.datetime.now().year
    return render_template('results.html', 
                           results=results, 
                           filename=filename,
                           current_year=current_year # Pass current_year
                          )


# Standard screen_file (non-SSE, synchronous)
@app.route('/screen', methods=['POST'])
def screen_file():
    if 'file' not in request.files: flash('No file part.', 'error'); return redirect(url_for('screening_actions_page'))
    file = request.files['file']
    if file.filename == '': flash('No selected file.', 'error'); return redirect(url_for('screening_actions_page'))
    
    if file and allowed_file(file.filename):
        results_list = []
        try:
            df = load_literature_ris(file.stream)
            if df is None or df.empty: raise ValueError("Failed to load RIS file or file is empty.")
            if 'abstract' not in df.columns: raise ValueError("'abstract' column missing.")
            if 'title' not in df.columns: df['title'] = pd.Series(["Title Not Found"] * len(df))
            else: df['title'] = df['title'].fillna("Title Not Found")
            if 'authors' not in df.columns: df['authors'] = pd.Series([[] for _ in range(len(df))])
            else: df['authors'] = df['authors'].apply(lambda x: x if isinstance(x, list) else [])
            
            criteria_prompt_text = get_screening_criteria()
            current_llm_config_data = get_current_llm_config(session)
            provider_name = current_llm_config_data['provider_name']
            model_id = current_llm_config_data['model_id']
            base_url = get_base_url_for_provider(provider_name)
            provider_info = get_llm_providers_info().get(provider_name, {})
            session_key_name = provider_info.get("api_key_session_key")
            api_key = session.get(session_key_name) if session_key_name else None
            if not api_key: flash(f"API Key for {provider_name} must be provided via the configuration form for this session.", "error"); return redirect(url_for('llm_config_page'))

            results_map = {}
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
                    future_to_index[future] = index

                for future in as_completed(futures):
                    index = future_to_index[future]
                    try:
                        screening_result = future.result()
                        if screening_result['decision'] == "CONFIG_ERROR":
                             flash(f"Config error for item at index {index}: {screening_result['reasoning']}", "error")
                             return redirect(url_for('llm_config_page'))
                        results_map[index] = screening_result
                    except Exception as exc:
                         print(f"Error processing item (index {index}) in sync route: {exc}")
                         traceback.print_exc()
                         results_map[index] = {'decision': 'WORKER_ERROR', 'reasoning': str(exc)}

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

            current_year = datetime.datetime.now().year
            return render_template('results.html', results=results_list, filename=file.filename, current_year=current_year)

        except Exception as e:
            traceback.print_exc(); flash(f"Error during direct screening: {e}", 'error')
            return redirect(url_for('screening_actions_page'))
    else:
        flash('Invalid file type.', 'error');
        return redirect(url_for('screening_actions_page'))


# --- New Test Screening SSE Route ---
@app.route('/stream_test_screen_file', methods=['POST'], endpoint='stream_test_screen_file')
def stream_test_screen_file():
    if 'file' not in request.files:
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'No file part.'})}\n\n", mimetype='text/event-stream')

    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'No selected/invalid file.'})}\n\n", mimetype='text/event-stream')

    try:
        sample_size = int(request.form.get('sample_size', 10))
        sample_size = max(5, min(50, sample_size))
    except ValueError: sample_size = 10

    try:
        df = load_literature_ris(file.stream)
        if df is None or df.empty:
            return Response(f"data: {json.dumps({'type': 'error', 'message': 'Failed to load RIS or file empty.'})}\n\n", mimetype='text/event-stream')
        if 'abstract' not in df.columns:
            return Response(f"data: {json.dumps({'type': 'error', 'message': 'RIS missing abstract column.'})}\n\n", mimetype='text/event-stream')
        df['title'] = df.get('title', pd.Series(["Title Not Found"] * len(df))).fillna("Title Not Found")
        df['authors'] = df.get('authors', pd.Series([[] for _ in range(len(df))]))
        df['authors'] = df['authors'].apply(lambda x: x if isinstance(x, list) else [])
        sample_df = df.head(min(sample_size, len(df)))
        actual_sample_size = len(sample_df)
        if actual_sample_size == 0:
             return Response(f"data: {json.dumps({'type': 'error', 'message': 'No entries found in the file to sample.'})}\n\n", mimetype='text/event-stream')

        criteria_prompt_text = get_screening_criteria()
        
        current_llm_config_data = get_current_llm_config(session)
        provider_name = current_llm_config_data['provider_name']
        model_id = current_llm_config_data['model_id']
        base_url = get_base_url_for_provider(provider_name)
        
        # --- ADDED: Explicit check for API Key in session --- 
        provider_info = get_llm_providers_info().get(provider_name, {})
        session_key_name = provider_info.get("api_key_session_key")
        api_key = session.get(session_key_name) if session_key_name else None

        if not api_key: # Checks if key is None or empty string
            error_message = f"API Key for {provider_name} must be provided via the configuration form for this session."
            return Response(f"data: {json.dumps({'type': 'error', 'message': error_message, 'needs_config': True})}\n\n", mimetype='text/event-stream')
        # --- End Session Key Check ---

        session_id = str(uuid.uuid4())
        test_sessions[session_id] = {
             'file_name': file.filename,
             'sample_size': actual_sample_size,
             'test_items_data': []
         }

        def generate_test_progress(): # Refactored with ThreadPoolExecutor
            processed_count = 0
            yield f"data: {json.dumps({'type': 'start', 'total': actual_sample_size})}\n\n"
            temp_results_list = []
            futures_map = {}
            
            with ThreadPoolExecutor(max_workers=8) as executor:
                for index, row in sample_df.iterrows():
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
                    abstract_text = row.get('abstract') # Needed for storing result
                    authors_list = row.get('authors', [])
                    authors_str = ", ".join(authors_list) if authors_list else "Authors Not Found"

                    try:
                        screening_result = future.result()
                        if screening_result['decision'] == "CONFIG_ERROR":
                            raise Exception(f"CONFIG_ERROR from worker: {screening_result['reasoning']}")

                        processed_count += 1
                        progress_percentage = int((processed_count / actual_sample_size) * 100)
                        item_id = str(uuid.uuid4())
                        test_item_template_data = {
                            'id': item_id, 'original_index': index, 'title': title,
                            'authors': authors_str, 'abstract': abstract_text,
                            'ai_decision': screening_result['decision'], 'ai_reasoning': screening_result['reasoning']
                        }
                        temp_results_list.append(test_item_template_data)
                        progress_data = {
                            'type': 'progress', 'count': processed_count, 'total': actual_sample_size,
                            'percentage': progress_percentage, 'current_item_title': title,
                            'decision': screening_result['decision']
                        }
                        yield f"data: {json.dumps(progress_data)}\n\n"

                    except Exception as e:
                        processed_count += 1
                        progress_percentage = int((processed_count / actual_sample_size) * 100)
                        error_message = f"Error processing item '{title[:30]}...': {e}"
                        print(f"Error processing item (index {index}): {e}")
                        traceback.print_exc()
                        progress_data = {
                             'type': 'progress', 'count': processed_count, 'total': actual_sample_size,
                             'percentage': progress_percentage, 'current_item_title': title,
                             'decision': 'THREAD_ERROR' 
                         }
                        yield f"data: {json.dumps(progress_data)}\n\n"
            
            temp_results_list.sort(key=lambda x: x.get('original_index', float('inf')))
            if session_id in test_sessions:
                 test_sessions[session_id]['test_items_data'] = temp_results_list
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Test screening finished.', 'session_id': session_id})}\n\n"

        return Response(generate_test_progress(), mimetype='text/event-stream')

    except Exception as e:
        traceback.print_exc()
        return Response(f"data: {json.dumps({'type': 'error', 'message': f'Server error before test streaming: {str(e)}'})}\n\n", mimetype='text/event-stream')


# --- New Route to Show Test Results ---
@app.route('/show_test_results/<session_id>', endpoint='show_test_results')
def show_test_results(session_id):
    if not session_id or session_id not in test_sessions:
        flash('Test session not found or expired. Please start a new test.', 'error')
        return redirect(url_for('screening_actions_page'))

    session_data = test_sessions.get(session_id)
    test_items = session_data.get('test_items_data')

    if not test_items: # If empty list or key missing
         flash('No test items found in session for display.', 'warning')
         # Maybe don't delete session here, let user try again?
         return redirect(url_for('screening_actions_page'))

    # We don't delete the session data here, because the user needs it
    # again potentially if they submit for metric calculation from test_results.html
    # Session data will be cleaned up eventually or when metrics are calculated/full screen started

    current_year = datetime.datetime.now().year
    return render_template('test_results.html',
                           test_items=test_items,
                           session_id=session_id, # Pass session_id for the metrics form
                           current_year=current_year)


# --- Run App ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5050)