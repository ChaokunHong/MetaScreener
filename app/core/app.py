import os
import pandas as pd
import time
import datetime  # Explicitly import datetime for current year
import uuid
import numpy as np
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
import fitz # PyMuPDF - ADDED for metadata title extraction
from apscheduler.schedulers.background import BackgroundScheduler # <-- Import APScheduler
import atexit # <-- To shut down scheduler gracefully
from datetime import timedelta # ADDED for session lifetime
from flask_redis import FlaskRedis
import pickle
from gevent import monkey, spawn, joinall # Import gevent utilities
monkey.patch_all() # Patch standard libraries to be gevent-friendly

# Celery integration
try:
    from app.celery_tasks.celery_app import celery
    from app.celery_tasks.tasks import (
        process_literature_screening, 
        process_pdf_screening, 
        process_quality_assessment,
        get_task_result,
        get_task_progress
    )
    CELERY_ENABLED = True
except ImportError as e:
    print(f"Celery not available: {e}")
    CELERY_ENABLED = False

# Initialize Redis client
redis_client = FlaskRedis()

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
from app.utils.utils import load_literature_ris, extract_text_from_pdf, construct_llm_prompt, call_llm_api, call_llm_api_raw_content, _parse_llm_response, call_llm_api_fast_test
from config.config import (
    get_screening_criteria, set_user_criteria, reset_to_default_criteria,
    USER_CRITERIA, # USER_CRITERIA is still used directly in app.py for session init, keep for now
    get_llm_providers_info, get_current_llm_config,
    get_api_key_for_provider, get_base_url_for_provider,
    DEFAULT_SYSTEM_PROMPT, DEFAULT_OUTPUT_INSTRUCTIONS,
    get_current_criteria_object,
    get_supported_criteria_frameworks, get_default_criteria_for_framework, get_current_framework_id,
    DEFAULT_FRAMEWORK_VALUES, # DEFAULT_EXAMPLE_CRITERIA, <-- Ensure this is removed
    get_blank_criteria_for_framework  # local import to avoid circular
)
# --- Import the new Blueprint ---
from app.quality_assessment_module import quality_bp
from app.quality_assessment_module.services import QUALITY_ASSESSMENT_TOOLS

app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')
# app.secret_key = os.urandom(24) # Old way
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'e8a3f2c9b7d5e6a1c3b8d7e9f0a2b5c7d8e9f1a3b6c8d0e2') # New way with example key
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False, # Set to True if your app is served over HTTPS
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    REDIS_URL=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    MAX_CONTENT_LENGTH=100 * 1024 * 1024  # 100MB max request size, should be sufficient for large datasets
)
redis_client.init_app(app)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'ris'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
test_sessions = {} # For holding test screening data + results before metrics
full_screening_sessions = {} # ADDED: For holding full screening results temporarily
# NEW: Use TTLCache for pdf_screening_results. Max 500 items, 2 hours TTL (7200 seconds)
pdf_screening_results = TTLCache(maxsize=500, ttl=7200)
pdf_extraction_results = {} # ADDED: For extraction results
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Redis session management functions
def store_test_session(session_id, data):
    try:
        redis_client.set(f"test_session:{session_id}", pickle.dumps(data), ex=86400)
    except Exception as e:
        app_logger.warning(f"Redis error in store_test_session: {e}")
    # Also store locally for local development compatibility
    test_sessions[session_id] = data

def get_test_session(session_id):
    try:
        data = redis_client.get(f"test_session:{session_id}")
        if data:
            return pickle.loads(data)
    except Exception as e:
        app_logger.warning(f"Redis error in get_test_session: {e}")
    # Fallback to in-memory storage
    return test_sessions.get(session_id)

def delete_test_session(session_id):
    try:
        redis_client.delete(f"test_session:{session_id}")
    except Exception as e:
        app_logger.warning(f"Redis error in delete_test_session: {e}")
    # Also remove from memory
    if session_id in test_sessions:
        del test_sessions[session_id]

def store_full_screening_session(screening_id, data):
    try:
        redis_client.set(f"full_screening:{screening_id}", pickle.dumps(data), ex=86400)
    except Exception as e:
        app_logger.warning(f"Redis error in store_full_screening_session: {e}")
    # Also store locally
    full_screening_sessions[screening_id] = data

def get_full_screening_session(screening_id):
    try:
        data = redis_client.get(f"full_screening:{screening_id}")
        if data:
            return pickle.loads(data)
    except Exception as e:
        app_logger.warning(f"Redis error in get_full_screening_session: {e}")
    # Fallback to in-memory storage
    return full_screening_sessions.get(screening_id)

# Initialize ThreadPoolExecutor
# Adjust max_workers based on your server capacity and typical workload
# For CPU-bound tasks in run_ai_quality_assessment (if any), ProcessPoolExecutor might be better,
# but for primarily I/O-bound (LLM API calls), ThreadPoolExecutor is usually fine.
# app.executor = ThreadPoolExecutor(max_workers=5) 

# --- Register the Blueprint ---
app.register_blueprint(quality_bp, url_prefix='/quality_assessment') # Fixed URL prefix to match template expectations


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

    # Check if the action is to clear a specific API key
    provider_to_clear = request.form.get('clear_api_key')
    if provider_to_clear:
        providers_info = get_llm_providers_info()
        if provider_to_clear in providers_info:
            provider_config_to_clear = providers_info[provider_to_clear]
            session_key_to_clear = provider_config_to_clear.get("api_key_session_key")
            if session_key_to_clear and session_key_to_clear in session:
                session.pop(session_key_to_clear)
                app_logger.info(f"Cleared API key for {provider_to_clear} from session.")
                flash(f'API Key for {provider_to_clear.replace("_"," ")} has been cleared from session.', 'success')
            else:
                app_logger.warning(f"Attempted to clear key for {provider_to_clear}, but no key found in session or session key name missing.")
                flash(f'No API Key was set in session for {provider_to_clear.replace("_"," ")}.', 'info')
        else:
            app_logger.warning(f"Attempted to clear key for invalid provider: {provider_to_clear}")
            flash(f'Invalid provider specified for clearing API key.', 'error')
        return redirect(url_for('llm_config_page')) # Redirect after clearing - REMAINS UNCHANGED FOR NOW

    # If not clearing, proceed with saving/updating LLM config and API key
    selected_provider = request.form.get('llm_provider')
    selected_model_id = request.form.get('llm_model_id')
    app_logger.info(f"Provider: {selected_provider}, Model: {selected_model_id}")

    providers_info = get_llm_providers_info()
    if not selected_provider or selected_provider not in providers_info:
        # For AJAX, this should also be a JSON response
        # flash('Invalid LLM Provider selected.', 'error') # Keep flash for non-JS fallback if any
        return jsonify({
            'status': 'error',
            'message': 'Invalid LLM Provider selected. Please select a valid provider.'
        }), 400 # Bad Request

    provider_config = providers_info[selected_provider]

    session['selected_llm_provider'] = selected_provider
    session['selected_llm_model_id'] = selected_model_id
    # flash_messages are now part of the JSON response message
    success_message_parts = [f'LLM Provider set to {selected_provider.replace("_"," ")} and Model to {selected_model_id}.']

    # Handle API key submission for the selected provider
    api_key_form_field = f"{selected_provider.lower()}_api_key"
    user_api_key = request.form.get(api_key_form_field)
    
    if user_api_key: # If user submitted a key for the currently selected provider
        app_logger.debug(f"Attempting to save API key for {selected_provider}.")
        session_key_for_api = provider_config.get("api_key_session_key")
        if session_key_for_api:
            session[session_key_for_api] = user_api_key
            app_logger.info(f"Saved API key for {selected_provider} into session.")
            success_message_parts.append(f'API Key for {selected_provider.replace("_"," ")} updated in session.')
        else:
             app_logger.error(f"Could not find api_key_session_key in provider config for {selected_provider}!")
             # This is an internal error, should be handled appropriately
             return jsonify({
                'status': 'error',
                'message': f'Error: Configuration problem for {selected_provider} API key storage.'
             }), 500 # Internal Server Error
    else:
        app_logger.debug(f"No new API key submitted for {selected_provider}. Retaining existing session key if any.")

    # If any key was set or LLM provider/model was changed, mark session as permanent
    if request.form.get('llm_provider') or any(key.endswith('_api_key') for key in request.form if request.form.get(key)):
        session.permanent = True

    app_logger.debug(f"Session contents after configure_llm: {session}")
    
    # NEW: Auto-test API key if one is available
    # Check if we have an API key for the selected provider (either from form or session)
    session_key_for_api = provider_config.get("api_key_session_key")
    api_key_to_test = user_api_key or (session.get(session_key_for_api) if session_key_for_api else None)
    
    if api_key_to_test:
        app_logger.info(f"Auto-testing API key for {selected_provider} after configuration save")
        
        # Get model for testing
        provider_models = providers_info[selected_provider].get('models', [])
        if provider_models:
            test_model_id = selected_model_id or provider_models[0]['id']
            base_url = get_base_url_for_provider(selected_provider)
            
            # Create test prompt
            if selected_provider in ["OpenAI_ChatGPT", "DeepSeek"]:
                test_prompt = {
                    "system_prompt": "You are a helpful AI assistant.",
                    "main_prompt": "Hello, please respond with 'OK' if you can receive this message. You may respond in json format if needed."
                }
            else:
                test_prompt = {
                    "system_prompt": "You are a helpful AI assistant.",
                    "main_prompt": "Hello, please respond with 'OK' if you can receive this message."
                }
            
            try:
                # Test the API key with fast test function
                api_result = call_llm_api_fast_test(test_prompt, selected_provider, test_model_id, api_key_to_test, base_url)
                
                if api_result and isinstance(api_result, str) and len(api_result) > 0 and not api_result.startswith("API_ERROR:"):
                    app_logger.info(f"Auto API key test successful for {selected_provider}")
                    final_success_message = " ".join(success_message_parts)
                    final_success_message += " API key validated successfully! Redirecting..."
                    
                    return jsonify({
                        'status': 'success',
                        'message': final_success_message,
                        'redirect_url': url_for('screening_criteria_page'),
                        'api_test_passed': True
                    }), 200
                else:
                    # API test failed
                    app_logger.warning(f"Auto API key test failed for {selected_provider}: {api_result}")
                    
                    # Provide specific error message based on the error
                    if isinstance(api_result, str):
                        if "401" in api_result or "unauthorized" in api_result.lower():
                            error_message = "API key is invalid or unauthorized. Please check your key."
                        elif "403" in api_result or "forbidden" in api_result.lower():
                            if selected_provider == "Anthropic_Claude":
                                error_message = "Claude API access forbidden. This could be due to invalid API key, insufficient balance, regional restrictions, or account issues."
                            else:
                                error_message = "API key does not have required permissions."
                        elif "429" in api_result or "rate limit" in api_result.lower() or "quota" in api_result.lower():
                            if selected_provider == "OpenAI_ChatGPT":
                                error_message = "OpenAI quota exceeded. Please check your billing and usage limits."
                            else:
                                error_message = "Rate limit or quota exceeded. Please check your account."
                        else:
                            error_message = "API key validation failed. Please verify your key is correct."
                    else:
                        error_message = "Unable to validate API key. Please check your key and try again."
                    
                    return jsonify({
                        'status': 'error',
                        'message': f'Configuration saved, but API key test failed: {error_message}',
                        'api_test_passed': False,
                        'show_manual_test': True
                    }), 200
                    
            except Exception as e:
                app_logger.error(f"Exception during auto API key test for {selected_provider}: {str(e)}")
                return jsonify({
                    'status': 'error',
                    'message': 'Configuration saved, but an error occurred while testing the API key. Please test manually.',
                    'api_test_passed': False,
                    'show_manual_test': True
                }), 200
        else:
            # No models available for testing
            final_success_message = " ".join(success_message_parts)
            final_success_message += " Configuration saved! (No models available for API testing)"
            
            return jsonify({
                'status': 'success',
                'message': final_success_message,
                'redirect_url': url_for('screening_criteria_page'),
                'api_test_passed': True
            }), 200
    else:
        # No API key to test - just save configuration
        final_success_message = " ".join(success_message_parts)
        final_success_message += " Configuration saved! Please add an API key to continue."
        
        return jsonify({
            'status': 'warning',
            'message': final_success_message,
            'api_test_passed': False,
            'show_manual_test': False,
            'needs_api_key': True
        }), 200


@app.route('/get_models_for_provider/<provider_name>')
def get_models_for_provider_route(provider_name):
    providers_info = get_llm_providers_info()
    if provider_name in providers_info:
        return jsonify(providers_info[provider_name]["models"])
    return jsonify([])


# --- Main Route --- (This is typically where the index route is)
@app.route('/')
def index():
    # return redirect(url_for('llm_config_page')) # Old: Redirect to LLM config
    return render_template('index.html', current_year=datetime.datetime.now().year) # New: Render the new landing page


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

# Route to test if an API key is valid
@app.route('/test_api_key', methods=['POST'])
def test_api_key():
    app_logger.info("--- Testing API Key --- ")
    
    # Basic request validation
    if not request.form.get('test_api_key'):
        return jsonify({
            'status': 'error',
            'message': 'Invalid request. Missing test_api_key parameter.'
        }), 400
    
    # Get provider and API key from request
    provider = request.form.get('provider', '').strip()
    api_key_field = f"{provider.lower()}_api_key" if provider else ''
    api_key = request.form.get(api_key_field, '').strip()
    
    # Enhanced input validation
    if not provider:
        return jsonify({
            'status': 'error',
            'message': 'Provider parameter is required.'
        }), 400
        
    if not api_key:
        return jsonify({
            'status': 'error',
            'message': 'API key is required.'
        }), 400
    
    # Validate API key format (basic checks)
    if len(api_key) < 10:
        return jsonify({
            'status': 'error',
            'message': 'API key appears to be too short. Please check your key.'
        }), 400
        
    if len(api_key) > 500:
        return jsonify({
            'status': 'error',
            'message': 'API key appears to be too long. Please check your key.'
        }), 400
    
    # Check for suspicious characters that might indicate injection attempts
    suspicious_chars = ['<', '>', '"', "'", ';', '--', '/*', '*/', 'DROP', 'SELECT', 'INSERT']
    if any(char in api_key.upper() for char in suspicious_chars):
        app_logger.warning(f"Suspicious API key test attempt from {request.remote_addr}: {api_key[:20]}...")
        return jsonify({
            'status': 'error',
            'message': 'Invalid API key format detected.'
        }), 400
    
    providers_info = get_llm_providers_info()
    if provider not in providers_info:
        return jsonify({
            'status': 'error',
            'message': f'Invalid provider: {provider}'
        }), 400
    
    # Get model for testing - use first available model or a specific test model
    provider_models = providers_info[provider].get('models', [])
    if not provider_models:
        return jsonify({
            'status': 'error',
            'message': f'No models available for {provider}'
        }), 400
    
    test_model_id = provider_models[0]['id']  # Use first model
    base_url = get_base_url_for_provider(provider)
    
    # Get optimized test configuration
    from config.config import API_TEST_CONFIG
    from app.utils.utils import call_llm_api_fast_test
    
    # Use optimized test prompts
    test_prompts = API_TEST_CONFIG.get("test_prompts", {})
    if provider in ["OpenAI_ChatGPT", "DeepSeek"]:
        test_prompt = test_prompts.get("json_compatible", {
            "system_prompt": "You are a helpful AI assistant. Respond in JSON format when requested.",
            "main_prompt": "Respond with {'status': 'OK'} to confirm you received this message."
        })
    else:
        test_prompt = test_prompts.get("simple", {
            "system_prompt": "You are a helpful assistant.",
            "main_prompt": "Respond with 'OK' to confirm you received this message."
        })
    
    try:
        # Test the API key with optimized fast test function
        app_logger.info(f"Fast testing API key for {provider} with model {test_model_id}")
        api_result = call_llm_api_fast_test(test_prompt, provider, test_model_id, api_key, base_url)
        
        if api_result and isinstance(api_result, str) and len(api_result) > 0 and not api_result.startswith("API_ERROR:"):
            app_logger.info(f"API key test successful for {provider}")
            return jsonify({
                'status': 'success',
                'message': f'API key for {provider.replace("_", " ")} is valid and working!'
            }), 200
        else:
            # Log the actual error but don't expose sensitive details to user
            app_logger.warning(f"API key test failed for {provider}: {api_result}")
            
            # Provide user-friendly error messages based on common error patterns
            if isinstance(api_result, str):
                if "401" in api_result or "unauthorized" in api_result.lower():
                    user_message = "API key is invalid or unauthorized. Please check your key."
                elif "403" in api_result or "forbidden" in api_result.lower():
                    if provider == "Anthropic_Claude":
                        user_message = "Claude API access forbidden. This could be due to: 1) Invalid API key, 2) Insufficient account balance, 3) No permission for this model, 4) Regional restrictions, or 5) Account suspension. Please check your account at https://console.anthropic.com/"
                    else:
                        user_message = "API key does not have required permissions."
                elif "429" in api_result or "rate limit" in api_result.lower() or "quota" in api_result.lower():
                    if provider == "OpenAI_ChatGPT":
                        user_message = "OpenAI quota exceeded. Please check your billing and usage limits at https://platform.openai.com/usage"
                    elif provider == "Anthropic_Claude":
                        user_message = "Claude API rate limit or quota exceeded. Please check your usage at https://console.anthropic.com/"
                    else:
                        user_message = "Rate limit or quota exceeded. Please try again later or check your account."
                elif "timeout" in api_result.lower():
                    user_message = "Request timed out. Please check your connection and try again."
                elif "billing" in api_result.lower():
                    if provider == "OpenAI_ChatGPT":
                        user_message = "OpenAI billing issue. Please check your payment method at https://platform.openai.com/account/billing"
                    elif provider == "Anthropic_Claude":
                        user_message = "Claude billing issue. Please check your account balance at https://console.anthropic.com/"
                    else:
                        user_message = "Billing issue detected. Please check your account."
                else:
                    user_message = "API key validation failed. Please verify your key is correct."
            else:
                user_message = "Unable to validate API key. Please check your key and try again."
            
            return jsonify({
                'status': 'error',
                'message': f'API key for {provider.replace("_", " ")} validation failed: {user_message}'
            }), 200
    except Exception as e:
        # Log the full error for debugging but provide generic message to user
        app_logger.error(f"Exception during API key test for {provider}: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while testing the API key. Please try again.'
        }), 200  # Still return 200 to handle error in frontend

@app.route('/criteria', methods=['GET'], endpoint='screening_criteria_page')
def screening_criteria_page():
    user_current_criteria = get_current_criteria_object() 
    current_framework_id = get_current_framework_id()

    # NEW: allow switching framework via query param
    all_frameworks = get_supported_criteria_frameworks()
    if not isinstance(all_frameworks, dict):
        app_logger.error(f"CRITICAL: get_supported_criteria_frameworks() in config.py returned a non-dictionary type: {type(all_frameworks)}. This may lead to errors. Defaulting to an empty dictionary for this request.")
        all_frameworks = {}
    
    requested_framework = request.args.get('framework_id')
    if requested_framework and all_frameworks and requested_framework in all_frameworks and requested_framework != current_framework_id:
        # Switch to requested framework & reset criteria to defaults for that framework
        # Use blank criteria so form starts empty
        set_user_criteria(requested_framework, get_blank_criteria_for_framework(requested_framework))
        current_framework_id = requested_framework
        user_current_criteria = get_current_criteria_object()

    current_year = datetime.datetime.now().year
    framework_default_criteria = get_default_criteria_for_framework(current_framework_id)

    # List of element prefixes (exclude 'other') for JS usage
    element_prefixes = [] # Default to empty list
    if all_frameworks and current_framework_id in all_frameworks and 'elements' in all_frameworks[current_framework_id]:
        element_prefixes = [el['id'] for el in all_frameworks[current_framework_id]['elements'] if el['id'] != 'other']

    # DEFAULT_FRAMEWORK_VALUES is now imported at the top of app.py

    config_defaults_for_template = {
        'DEFAULT_SYSTEM_PROMPT': DEFAULT_SYSTEM_PROMPT,
        'DEFAULT_OUTPUT_INSTRUCTIONS': DEFAULT_OUTPUT_INSTRUCTIONS
    }

    return render_template('screening_criteria.html', 
                           criteria=user_current_criteria, 
                           current_year=current_year,
                           config_defaults=config_defaults_for_template,
                           supported_frameworks=all_frameworks,
                           current_framework_id=current_framework_id,
                           default_framework_criteria=framework_default_criteria,
                           element_prefixes=element_prefixes)

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
    return render_template('screening_actions.html',  # <--- Ensure this points to screening_actions.html
                           current_year=current_year)
                           # current_llm_provider=current_llm['provider_name'] # if needed


# --- Criteria Routes ---
@app.route('/set_criteria', methods=['POST'])
def set_criteria():
    try:
        selected_framework = request.form.get('framework_id', get_current_framework_id())
        supported_frameworks = get_supported_criteria_frameworks()
        if selected_framework not in supported_frameworks:
            flash(f"Unknown framework '{selected_framework}'.", 'error')
            return redirect(url_for('screening_criteria_page'))

        framework_config = supported_frameworks[selected_framework]

        # Dynamically gather criteria fields based on framework definition
        criteria_dict = {}
        for element in framework_config.get('elements', []):
            el_id = element['id']
            if el_id == 'other':
                criteria_dict['other_inclusion'] = request.form.get('other_inclusion', '')
                criteria_dict['other_exclusion'] = request.form.get('other_exclusion', '')
            else:
                for aspect in ['include', 'exclude', 'maybe']:
                    form_key = f"{el_id}_{aspect}"
                    criteria_dict[form_key] = request.form.get(form_key, '')

        # Advanced settings
        system_prompt = request.form.get('ai_system_prompt')
        output_instructions = request.form.get('ai_output_format_instructions')
        if system_prompt is not None:
            criteria_dict['ai_system_prompt'] = system_prompt
        if output_instructions is not None:
            criteria_dict['ai_output_format_instructions'] = output_instructions

        # Persist criteria for the user
        set_user_criteria(selected_framework, criteria_dict)
        # Return JSON response for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'status': 'success',
                'message': 'Screening criteria and settings successfully saved! Redirecting...',
                'redirect_url': url_for('screening_actions_page')
            }), 200
        # Standard redirect for non-AJAX requests
        flash('Screening criteria and settings successfully saved!', 'success')
        return redirect(url_for('screening_actions_page')) # New redirect to screening actions page
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'status': 'error',
                'message': f'Error saving screening criteria: {e}'
            }), 500
        flash(f'Error saving screening criteria: {e}', 'error')
        app_logger.exception("Error saving screening criteria") # Replaces traceback.print_exc()
        return redirect(url_for('screening_criteria_page'))


@app.route('/reset_criteria')
def reset_criteria():
    reset_to_default_criteria()
    flash('Screening criteria have been reset to default values.', 'info')
    return redirect(url_for('screening_criteria_page')) # MODIFIED REDIRECT


# --- Screening Logic Helper ---
def _perform_screening_on_abstract(abstract_text, criteria_prompt_text, provider_name, model_id, api_key, base_url, 
                                  item_index=None, max_retry_attempts=3):
    """
    Perform screening on a single abstract with enhanced error handling and retry logic.
    
    Args:
        abstract_text: The abstract text to screen
        criteria_prompt_text: The screening criteria
        provider_name: LLM provider name
        model_id: Model identifier
        api_key: API key for the provider
        base_url: Base URL for the API
        item_index: Index of the item being processed (for logging)
        max_retry_attempts: Maximum number of retry attempts
        
    Returns:
        Dictionary with decision and reasoning
    """
    from app.utils.utils import handle_screening_error, should_retry_error, get_retry_delay, handle_processing_error_recovery
    from gevent import sleep
    
    func_start_time = time.time()
    if item_index is not None:
        app_logger.info(f"PERF: _perform_screening_on_abstract started for item {item_index}, abstract: {abstract_text[:50]}...")
    else:
        app_logger.info(f"PERF: _perform_screening_on_abstract started for abstract: {abstract_text[:50]}...")

    # Track error counts for this item
    attempt_count = 0
    last_error = None
    
    while attempt_count < max_retry_attempts:
        attempt_count += 1
        
        try:
            # Check if essential config is provided
            if not api_key:
                return {"decision": "CONFIG_ERROR", "reasoning": f"API Key for {provider_name} missing in call."}

            ai_decision = "ERROR"
            ai_reasoning = "An unexpected error occurred during AI screening."

            if pd.isna(abstract_text) or not abstract_text or not isinstance(abstract_text, str) or abstract_text.strip() == "":
                ai_decision = "NO_ABSTRACT"
                ai_reasoning = "Abstract is missing or empty."
            else:
                prompt_construct_start_time = time.time()
                prompt = construct_llm_prompt(abstract_text, criteria_prompt_text)
                prompt_construct_end_time = time.time()
                app_logger.info(f"PERF: construct_llm_prompt took {prompt_construct_end_time - prompt_construct_start_time:.4f} seconds.")

                if prompt:
                    llm_call_start_time = time.time()
                    # Use passed-in parameters for the API call
                    api_result = call_llm_api(prompt, provider_name, model_id, api_key, base_url)
                    llm_call_end_time = time.time()
                    app_logger.info(f"PERF: call_llm_api for provider {provider_name} model {model_id} took {llm_call_end_time - llm_call_start_time:.4f} seconds.")

                    if api_result and isinstance(api_result, dict):
                        ai_decision = api_result.get('label', 'API_ERROR')
                        ai_reasoning = api_result.get('justification', 'API call failed or returned invalid data.')
                        
                        # Check if the result indicates an error that should be retried
                        if ai_decision in ['API_TIMEOUT', 'API_HTTP_ERROR_N/A', 'SCRIPT_ERROR'] and attempt_count < max_retry_attempts:
                            # Create a mock error for the error handler
                            mock_error = Exception(f"API returned error decision: {ai_decision} - {ai_reasoning}")
                            error_result = handle_screening_error(
                                mock_error, item_index or 0, provider_name, attempt_count, max_retry_attempts
                            )
                            
                            if should_retry_error(error_result):
                                delay = get_retry_delay(error_result, attempt_count)
                                app_logger.info(f"API error detected, retrying in {delay:.2f}s (attempt {attempt_count}/{max_retry_attempts})")
                                sleep(delay)
                                continue
                            else:
                                # Return the error handling result
                                return {"decision": error_result["decision"], "reasoning": error_result["reasoning"]}
                    else:
                        ai_decision = "API_ERROR"
                        ai_reasoning = "API call function returned None or malformed data structure."
                else:
                    ai_decision = "PROMPT_ERROR"
                    ai_reasoning = "Failed to construct LLM prompt."
            
            # If we reach here, the processing was successful
            func_end_time = time.time()
            if attempt_count > 1:
                app_logger.info(f"PERF: _perform_screening_on_abstract succeeded on attempt {attempt_count} in {func_end_time - func_start_time:.4f} seconds. Decision: {ai_decision}")
            else:
                app_logger.info(f"PERF: _perform_screening_on_abstract finished in {func_end_time - func_start_time:.4f} seconds. Decision: {ai_decision}")
            
            return {"decision": ai_decision, "reasoning": ai_reasoning}
        
        except Exception as e:
            last_error = e
            
            # Use the enhanced error handling
            error_result = handle_screening_error(e, item_index or 0, provider_name, attempt_count, max_retry_attempts)
            
            # Check if this is a critical error that should stop processing immediately
            if error_result["decision"] == "CRITICAL_ERROR":
                app_logger.error(f"Critical error in _perform_screening_on_abstract: {str(e)}")
                return error_result
            
            # Check if we should retry
            if should_retry_error(error_result) and attempt_count < max_retry_attempts:
                delay = get_retry_delay(error_result, attempt_count)
                app_logger.info(f"Retrying _perform_screening_on_abstract in {delay:.2f}s (attempt {attempt_count + 1}/{max_retry_attempts})")
                sleep(delay)
                continue
            else:
                # Max attempts reached or error should not be retried
                app_logger.warning(f"_perform_screening_on_abstract failed after {attempt_count} attempts: {str(e)}")
                return error_result
    
    # If we exit the loop without success, return the last error result
    if last_error:
        final_error_result = handle_screening_error(last_error, item_index or 0, provider_name, max_retry_attempts, max_retry_attempts)
        app_logger.error(f"_perform_screening_on_abstract failed after all {max_retry_attempts} attempts: {str(last_error)}")
        
        # NEW: Attempt recovery for PROCESSING_ERROR
        if final_error_result.get("decision") == "PROCESSING_ERROR":
            app_logger.info(f"Attempting recovery for PROCESSING_ERROR on item {item_index}")
            item_data = {
                'abstract': abstract_text,
                'title': f"Item {item_index}" if item_index else "Unknown Item"
            }
            recovery_result = handle_processing_error_recovery(
                final_error_result, item_data, provider_name, model_id, api_key, base_url, criteria_prompt_text
            )
            return recovery_result
        
        return final_error_result
    else:
        # This should not happen, but provide a fallback
        return {"decision": "UNKNOWN_ERROR", "reasoning": "Processing failed for unknown reasons after all retry attempts."}


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
    session_data = get_test_session(session_id)
    if not session_data:
        flash('Test session not found or expired.', 'error')
        return redirect(url_for('abstract_screening_page'))
    
    df = session_data.get('df')
    filename = session_data.get('file_name')
    if df is None or df.empty: # Added df.empty check
        flash('Test session data missing dataframe or dataframe is empty.', 'error')
        # delete_test_session(session_id) # Optional: clean up if df is bad
        return redirect(url_for('abstract_screening_page'))
    
    results_list = []
    try:
        # Pre-fetch configuration that doesn't change per item
        criteria_prompt_text = get_screening_criteria()
        current_llm_config_data = get_current_llm_config(session)
        provider_name = current_llm_config_data['provider_name']
        model_id = current_llm_config_data['model_id']
        base_url = get_base_url_for_provider(provider_name)
        provider_info = get_llm_providers_info().get(provider_name, {})
        session_key_name = provider_info.get("api_key_session_key")
        api_key = session.get(session_key_name) if session_key_name else None

        if not api_key: 
            flash(f"API Key for {provider_name} must be provided via the configuration form for this session.", "error")
            delete_test_session(session_id) 
            return redirect(url_for('llm_config_page'))

        results_map = {}
        
        # --- Using gevent.spawn for concurrency ---
        greenlets = []
        app_logger.info(f"Screening {len(df)} abstracts for session {session_id} using gevent.")
        for index, row in df.iterrows():
            abstract = row.get('abstract')
            greenlet = spawn(_perform_screening_on_abstract,
                             abstract, criteria_prompt_text,
                             provider_name, model_id, api_key, base_url, index)
            greenlets.append((index, row, greenlet))

        # Wait for all greenlets to complete, with a timeout
        # Nginx read_timeout for this path is 600s. Gunicorn timeout is 3600s.
        # gevent joinall timeout should be less than Nginx's to allow graceful handling.
        join_timeout = 580 
        app_logger.info(f"Waiting for {len(greenlets)} greenlets to complete with timeout {join_timeout}s.")
        joinall(greenlets_to_join=[glet for _, glet in greenlets], timeout=join_timeout)
        app_logger.info("Greenlet join completed or timed out.")

        processed_count = 0
        for index, greenlet in greenlets:
            try:
                if greenlet.ready(): # Check if greenlet has finished (successfully or with error)
                    if greenlet.successful(): # Check if greenlet completed without unhandled exception
                        screening_result = greenlet.get(block=False) # Non-blocking get as it's ready
                        if screening_result.get('decision') == "CONFIG_ERROR": # Use .get for safety
                             app_logger.error(f"Config error for item at index {index} (session {session_id}): {screening_result.get('reasoning')}")
                        results_map[index] = screening_result
                    else: # Greenlet died due to an unhandled exception in _perform_screening_on_abstract
                        app_logger.error(f"Unhandled exception in greenlet for item (index {index}, session {session_id}): {greenlet.exception}")
                        results_map[index] = {'decision': 'GREENLET_ERROR', 'reasoning': str(greenlet.exception)}
                else: # Greenlet did not finish (e.g. joinall timed out)
                    app_logger.warning(f"Greenlet for item (index {index}, session {session_id}) did not complete within timeout.")
                    results_map[index] = {'decision': 'TIMEOUT_ERROR', 'reasoning': 'Processing timed out.'}
            except Exception as exc: 
                 app_logger.error(f"Error processing result from greenlet for item (index {index}, session {session_id}): {exc}")
                 app_logger.exception(f"Exception details for item (index {index}, session {session_id}) during greenlet result processing")
                 results_map[index] = {'decision': 'PROCESSING_ERROR', 'reasoning': str(exc)}
            processed_count +=1
        
        app_logger.info(f"Finished processing results for {processed_count}/{len(df)} items for session {session_id}.")
        # --- End gevent concurrency block ---

        # Reconstruct results_list in original order
        for index, row in df.iterrows():
             result_data = results_map.get(index)
             if result_data:
                  results_list.append({
                      'index': index + 1, 
                      'title': row.get('title', "N/A"),
                      'authors': ", ".join(row.get('authors', [])) if isinstance(row.get('authors'), list) else "Authors Not Found",
                      'decision': result_data.get('decision', 'UNKNOWN_ERROR'),
                      'reasoning': result_data.get('reasoning', 'No reasoning provided')
                  })
             else: 
                 app_logger.warning(f"Missing result for item (index {index}, session {session_id}) when reconstructing list.")
                 results_list.append({
                     'index': index + 1,
                     'title': row.get('title', "N/A"),
                     'authors': ", ".join(row.get('authors', [])) if isinstance(row.get('authors'), list) else "Authors Not Found",
                     'decision': 'MISSING_RESULT',
                     'reasoning': 'The screening result for this item was not processed or found.'
                 })

        # Generate a unique screening ID for results storage
        screening_id = str(uuid.uuid4())
        
        # Store results for download functionality
        store_full_screening_session(screening_id, {
            'filename': filename, 
            'results': results_list,
            'filter_applied': 'all entries'
        })
        
        delete_test_session(session_id)
        current_year = datetime.datetime.now().year
        app_logger.info(f"Successfully completed screening for session {session_id}. Rendering results with screening_id {screening_id}.")
        return render_template('results.html', results=results_list, filename=filename, screening_id=screening_id, current_year=current_year)

    except Exception as e:
        app_logger.exception(f"Critical error during full screening for session {session_id}")
        flash(f"An unexpected error occurred during the screening process. Please check logs. Error: {type(e).__name__}", 'error')
        if 'session_id' in locals() and session_id: 
            delete_test_session(session_id)
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
    if not session_id:
        flash('Test session ID not provided.', 'error')
        return redirect(url_for('abstract_screening_page'))
        
    session_data = get_test_session(session_id)
    if not session_data:
        flash('Test session not found or expired.', 'error')
        return redirect(url_for('abstract_screening_page'))

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
    
    # Update session data with metrics results
    session_data['full_metrics_results'] = results_data
    store_test_session(session_id, session_data)

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
    start_data = {'type': 'start', 'total': total_items}
    yield f"data: {json.dumps(start_data)}\n\n"
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
            # Reduce sleep time to increase UI update frequency
            time.sleep(0.005) # Previously 0.02, now much lower for better responsiveness
    except Exception as e:
        error_message = f"Error during item processing: {str(e)}"
        error_data = {'type': 'error', 'message': error_message}
        yield f"data: {json.dumps(error_data)}\n\n"
        traceback.print_exc()
        return

    complete_data = {'type': 'complete', 'message': 'Screening finished.'}
    yield f"data: {json.dumps(complete_data)}\n\n"


@app.route('/stream_screen_file', methods=['POST'])
def stream_screen_file():
    if 'file' not in request.files:
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'No file part.'})}\n\n", mimetype='text/event-stream')
    
    uploaded_file_full = request.files['file']
    if uploaded_file_full.filename == '':
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'No selected file.'})}\n\n", mimetype='text/event-stream')
    if not allowed_file(uploaded_file_full.filename):
        return Response(f"data: {json.dumps({'type': 'error', 'message': 'Invalid file type.'})}\n\n", mimetype='text/event-stream')

    line_range_input_val = request.form.get('line_range_filter', '').strip()
    title_filter_input_val = request.form.get('title_text_filter', '').strip()
    
    # Get resume ID if available (new lightweight resuming mechanism)
    resume_id = request.form.get('resume_id', '')
    resume_from = 0
    previously_processed_items = []
    
    # If resume ID is provided, load the saved state from server
    if resume_id:
        state_key = f"state_{resume_id}"
        saved_state = get_full_screening_session(state_key)
        
        if saved_state:
            app_logger.info(f"Resuming screening from saved state with ID: {resume_id}")
            resume_from = saved_state.get('resume_point', 0)
            previously_processed_items = saved_state.get('processed_items', [])
            
            # Try to use saved filter info if not provided in request
            saved_filters = saved_state.get('filter_info', {})
            if not line_range_input_val and saved_filters.get('line_range'):
                line_range_input_val = saved_filters['line_range'] 
            if not title_filter_input_val and saved_filters.get('title_filter'):
                title_filter_input_val = saved_filters['title_filter']
        else:
            app_logger.warning(f"Resume ID {resume_id} not found or expired")
            return Response(f"data: {json.dumps({'type': 'error', 'message': 'Resume data not found or expired. Please start a new screening session.'})}\n\n", mimetype='text/event-stream')
    else:
        # Legacy resuming - will only handle small datasets
        # Handle resume parameters
        is_resume = request.form.get('resume', '').lower() == 'true'
        if is_resume and request.form.get('resume_from'):
            try:
                resume_from = int(request.form.get('resume_from'))
                app_logger.info(f"Resume requested with resume_from={resume_from}")
            except ValueError:
                app_logger.warning(f"Invalid resume_from value: {request.form.get('resume_from')}")
                resume_from = 0
        
        # Get previously processed items, if resuming
        if is_resume and request.form.get('processed_data'):
            try:
                previously_processed_items = json.loads(request.form.get('processed_data'))
                app_logger.info(f"Loaded {len(previously_processed_items)} previously processed items for resume")
            except json.JSONDecodeError:
                app_logger.warning("Failed to parse processed_data JSON")
                previously_processed_items = []

    criteria_prompt_text_val_full = get_screening_criteria()
    current_llm_config_data_val_full = get_current_llm_config(session)
    provider_name_val_full = current_llm_config_data_val_full['provider_name']
    model_id_val_full = current_llm_config_data_val_full['model_id']
    base_url_val_full = get_base_url_for_provider(provider_name_val_full)
    provider_info_val_full = get_llm_providers_info().get(provider_name_val_full, {})
    session_key_name_val_full = provider_info_val_full.get("api_key_session_key")
    api_key_val_full = session.get(session_key_name_val_full) if session_key_name_val_full else None
    
    original_filename_for_session = uploaded_file_full.filename
    temp_file_path_full_screen = os.path.join(UPLOAD_FOLDER, f"temp_full_sse_{uuid.uuid4()}.ris")
    
    try:
        uploaded_file_full.save(temp_file_path_full_screen)
        app_logger.info(f"SSE Full screening: Uploaded file saved to temporary path: {temp_file_path_full_screen}")
    except Exception as e_save:
        app_logger.error(f"SSE Full screening: Failed to save uploaded file initially: {e_save}")
        return Response(f"data: {json.dumps({'type': 'error', 'message': f'Failed to save uploaded file: {e_save}'})}\n\n", mimetype='text/event-stream')

    def generate_response(line_range_filter, title_text_filter, saved_temp_file_path, original_filename,
                          criteria_prompt, llm_provider, llm_model, llm_base_url, llm_api_key_from_outer_scope,
                          is_resuming=False, resume_position=0, previous_results=None):
        # Import gevent.sleep
        from gevent import sleep
        
        overall_start_time = time.time()
        app_logger.info(f"PERF SSE: generate_response (full screen SSE) started for {original_filename}.")
        current_temp_file_path = saved_temp_file_path
        
        yield f"data: {json.dumps({'type': 'init', 'message': 'Processing upload, please wait...'})}\n\n"
        
        try:
            line_range_input = line_range_filter
            title_filter_input = title_text_filter

            yield f"data: {json.dumps({'type': 'status', 'message': 'Reading and parsing file content...'})}\n\n"
            
            with open(current_temp_file_path, 'rb') as f_stream:
                 df = load_literature_ris(f_stream)
            
            if df is None or df.empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to load RIS or file empty.'})}\n\n"
                return
            if 'abstract' not in df.columns:
                yield f"data: {json.dumps({'type': 'error', 'message': 'RIS missing abstract column.'})}\n\n"
                return
            
            yield f"data: {json.dumps({'type': 'status', 'message': 'File parsed. Preparing data for screening...'})}\n\n"
            
            df['title'] = df.get('title', pd.Series(["Title Not Found"] * len(df))).fillna("Title Not Found")
            df['authors'] = df.get('authors', pd.Series([[] for _ in range(len(df))]))
            df['authors'] = df['authors'].apply(lambda x: x if isinstance(x, list) else [])

            df_for_screening = df.copy()
            original_df_count = len(df)
            filter_description = "all entries"

            if title_filter_input:
                df_for_screening = df_for_screening[df_for_screening['title'].str.contains(title_filter_input, case=False, na=False)]
                filter_description = f"entries matching title '{title_filter_input}'"
                if df_for_screening.empty:
                    message_text = f'No articles found matching title: "{title_filter_input}"'
                    yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
                    return
            elif line_range_input:
                try:
                    start_idx, end_idx = parse_line_range(line_range_input, original_df_count)
                    if start_idx >= end_idx:
                        message_text = f'The range "{line_range_input}" is invalid or results in no articles.'
                        yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
                        return
                    df_for_screening = df_for_screening.iloc[start_idx:end_idx]
                    filter_description = f"entries in 1-based range [{start_idx + 1}-{end_idx}]"
                    if df_for_screening.empty:
                        message_text = f'The range "{line_range_input}" resulted in no articles to screen.'
                        yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
                        return
                except ValueError as e:
                    message_text = f'Invalid range format for "{line_range_input}": {str(e)}'
                    yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
                    return
            
            total_entries_to_screen = len(df_for_screening)
            
            # If resuming, inform the user and update the progress status
            if resume_position > 0 and previous_results and len(previous_results) > 0:
                progress_message = f"Resuming screening from position {resume_position} / {total_entries_to_screen}"
                yield f"data: {json.dumps({'type': 'status', 'message': progress_message})}\n\n"
                app_logger.info(f"Resuming screening for {original_filename} from position {resume_position}")
            else:
                yield f"data: {json.dumps({'type': 'status', 'message': f'Preparing to screen {total_entries_to_screen} entries.'})}\n\n"

            if not llm_api_key_from_outer_scope:
                yield f"data: {json.dumps({'type': 'error', 'message': f'API Key for {llm_provider} must be provided.', 'needs_config': True})}\n\n"
                return 

            screening_id = str(uuid.uuid4())
            yield f"data: {json.dumps({'type': 'start', 'total': total_entries_to_screen, 'filter_info': filter_description})}\n\n"
            
            app_logger.info(f"PERF SSE: Processing {total_entries_to_screen} items for file {original_filename} using smart batch processing.")
            
            # Smart batch processing system
            # Adaptive parameters - optimize for speed and responsive UI updates
            active_batch_size = min(30, total_entries_to_screen)  # Use larger batch size for better performance
            max_concurrent = 50  # Higher concurrency for faster processing
            batch_delay = 0.0  # No delay between batches
            error_backoff = 1.5  # Error backoff multiplier
            
            # Track rate limit errors
            rate_limit_errors = 0
            
            # Prepare items for processing
            to_process = []
            temp_results_list = []
            
            # If resuming processing, we should:
            # 1. Add previously processed items to the results list
            # 2. Only process items from the resume point
            processed_count = 0
            
            # Create a mapping of index to result item for deduplication
            processed_indices = {}
            
            if is_resuming and resume_position > 0:
                app_logger.info(f"Resuming from position {resume_position} for {original_filename}")
                
                # Add previously processed items to results list if available
                if previous_results and len(previous_results) > 0:
                    # First create index mapping to track which items have been processed
                    for result_item in previous_results:
                        item_index = result_item.get('index')
                        if item_index is not None:
                            processed_indices[item_index] = result_item
                    
                    # Use mapping values rather than directly extending
                    temp_results_list.extend(processed_indices.values())
                    processed_count = len(processed_indices)
                    
                    # Log the indices that have been processed for debugging
                    processed_index_list = sorted(list(processed_indices.keys()))
                    index_summary = f"First: {processed_index_list[:5]}, Last: {processed_index_list[-5:] if len(processed_index_list) > 5 else []}"
                    app_logger.info(f"Added {processed_count} previous unique results (from {len(previous_results)} total). Indices: {index_summary}")
                else:
                    app_logger.warning(f"Resume position {resume_position} provided but no previous results available")
                
                # Check if resume_position is consistent with processed_count
                if abs(resume_position - processed_count) > 1:
                    app_logger.warning(f"Resume position ({resume_position}) doesn't match processed count ({processed_count}) - adjusting to prevent data loss")
                    resume_position = min(resume_position, processed_count)
                
                # Only add items from resume point to process list
                items_added_for_processing = 0
                index_counter = 0
                
                # Create index_to_add set to track which indices need to be added
                indices_to_add = set()
                
                # First, scan through all items to identify which ones need to be added
                for index, row in df_for_screening.iterrows():
                    actual_index = index + 1  # 1-based index as used in the UI
                    if index_counter >= resume_position and actual_index not in processed_indices:
                        indices_to_add.add(index)
                    index_counter += 1
                
                # Then add items in the original order
                for index, row in df_for_screening.iterrows():
                    if index in indices_to_add:
                        to_process.append((index, row))
                        items_added_for_processing += 1
                
                app_logger.info(f"Added {items_added_for_processing} new items to process list starting from position {resume_position}")
                
                # Update progress for already processed items
                progress_percentage = int((processed_count / total_entries_to_screen) * 100) if total_entries_to_screen > 0 else 0
                status_message = f"Restored {processed_count} previously processed items. Continuing from item {resume_position+1}."
                yield f"data: {json.dumps({'type': 'status', 'message': status_message})}\n\n"
                
                yield f"data: {json.dumps({'type': 'progress', 'count': processed_count, 'total': total_entries_to_screen, 'percentage': progress_percentage})}\n\n"
            else:
                # Not resuming or invalid resume position - normal processing, prepare all items
                app_logger.info(f"Starting fresh screening for {original_filename} with {total_entries_to_screen} items")
                for index, row in df_for_screening.iterrows():
                    to_process.append((index, row))
            
            # Use immediate updates without queue or timer
            
            # Process items in batches
            while to_process:
                # Extract current batch
                current_batch = to_process[:active_batch_size]
                to_process = to_process[active_batch_size:]
                
                # Launch greenlets for current batch
                batch_greenlets = []
                batch_429_errors = 0  # Count 429 errors in this batch
                
                for index, row in current_batch:
                    abstract = row.get('abstract')
                    greenlet = spawn(_perform_screening_on_abstract,
                                    abstract, criteria_prompt,
                                    llm_provider, llm_model, 
                                    llm_api_key_from_outer_scope, llm_base_url, index)
                    batch_greenlets.append((index, row, greenlet))
                
                # Optimize: Use reasonable timeout for DeepSeek reasoner model
                max_wait_time = 90 # 90 seconds timeout - DeepSeek reasoner needs 20-40s per call
                check_interval = 0.5 # Check every 0.5 seconds
                force_timeout = 120 # 120 seconds absolute maximum before force kill
                checks_completed = 0
                max_checks = int(max_wait_time / check_interval)
                
                completed_indices = set()
                
                # Check results frequently for immediate UI updates
                while checks_completed < max_checks and len(completed_indices) < len(batch_greenlets):
                    # Brief wait
                    sleep(check_interval)
                    checks_completed += 1
                    
                    # Check completed greenlets and send immediate updates
                    for idx, (index, row, greenlet) in enumerate(batch_greenlets):
                        if idx in completed_indices:
                            continue  # Already processed this greenlet
                            
                        if greenlet.ready():
                            completed_indices.add(idx)
                            
                            title = row.get('title', "N/A")
                            authors_list = row.get('authors', [])
                            authors_str = ", ".join(authors_list) if authors_list else "Authors Not Found"
                            
                            # Process result with enhanced error handling
                            try:
                                if greenlet.successful():
                                    screening_result = greenlet.get(block=False)
                                    
                                    # Check if greenlet was killed and returned GreenletExit
                                    if hasattr(screening_result, '__class__') and 'GreenletExit' in str(type(screening_result)):
                                        app_logger.warning(f"Greenlet for item {index} was terminated (GreenletExit)")
                                        processing_error_result = {'decision': 'PROCESSING_ERROR', 'reasoning': 'Processing was terminated due to timeout or system constraints'}
                                        
                                        # Attempt recovery for terminated greenlet
                                        app_logger.info(f"Attempting recovery for terminated greenlet on item {index}")
                                        from app.utils.utils import handle_processing_error_recovery
                                        item_data = {
                                            'abstract': row.get('abstract', ''),
                                            'title': row.get('title', f"Item {index}")
                                        }
                                        screening_result = handle_processing_error_recovery(
                                            processing_error_result, item_data, llm_provider_param, llm_model_param, 
                                            llm_api_key_from_outer_scope, llm_base_url_param, criteria_prompt_param
                                        )
                                    
                                    # Ensure screening_result is a dictionary
                                    elif not isinstance(screening_result, dict):
                                        app_logger.warning(f"Invalid screening result type for item {index}: {type(screening_result)}")
                                        screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Invalid result type: {type(screening_result)}'}
                                    
                                    # Fast detection of network errors - auto skip to prevent hang
                                    elif (screening_result.get('decision') in ['API_HTTP_ERROR_N/A', 'API_TIMEOUT', 'API_ERROR'] and 
                                        ('Network error' in str(screening_result.get('reasoning', '')) or 
                                         'ConnectionError' in str(screening_result.get('reasoning', '')) or
                                         'ChunkedEncodingError' in str(screening_result.get('reasoning', '')) or
                                         'timeout' in str(screening_result.get('reasoning', '')).lower())):
                                        app_logger.warning(f"Network error detected for item {index}, auto-skipping: {screening_result.get('reasoning', '')}")
                                        screening_result = {'decision': 'NETWORK_ERROR', 'reasoning': 'Network error - automatically skipped to prevent hang'}
                                    
                                    # Detect 429 errors
                                    elif (screening_result.get('decision') == 'API_ERROR' and 
                                        '429' in str(screening_result.get('reasoning', ''))):
                                        batch_429_errors += 1
                                else:
                                    # Handle timeout or failure
                                    error_msg = str(greenlet.exception) if greenlet.exception else "Processing error"
                                    screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': error_msg}
                            except Exception as e:
                                # Handle any unexpected errors during result processing
                                app_logger.error(f"Error processing greenlet result for item {index}: {e}")
                                screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Error processing result: {str(e)}'}
                            
                            # Save result
                            output_data = {
                                'index': index + 1, 
                                'title': title, 
                                'authors': authors_str,
                                'decision': screening_result.get('decision', 'ITEM_ERROR'), 
                                'reasoning': screening_result.get('reasoning', 'Error retrieving result.'),
                                'abstract': row.get('abstract', '')
                            }
                            
                            # Check if result item with same index already exists
                            item_index = output_data['index']
                            existing_item_index = next((i for i, item in enumerate(temp_results_list) 
                                                       if item.get('index') == item_index), -1)
                            
                            if existing_item_index >= 0:
                                # If already exists, replace it
                                app_logger.info(f"Replacing existing result with index {item_index}")
                                temp_results_list[existing_item_index] = output_data
                            else:
                                # Otherwise add new item
                                temp_results_list.append(output_data)
                            
                            # Update progress and send immediate UI event
                            processed_count += 1
                            progress_percentage = int((processed_count / total_entries_to_screen) * 100)
                            
                            progress_event = {
                                'type': 'progress', 
                                'count': processed_count, 
                                'total': total_entries_to_screen,
                                'percentage': progress_percentage, 
                                'current_item_title': title,
                                'decision': screening_result.get('decision', 'ITEM_ERROR'),
                                'item_data': output_data
                            }
                            
                            # Send immediate update for real-time feedback
                            yield f"data: {json.dumps(progress_event)}\n\n"
                            
                            # Send status updates frequently for better UI responsiveness
                            if processed_count % 1 == 0:
                                remaining = len(to_process) + (len(batch_greenlets) - len(completed_indices))
                                total = total_entries_to_screen
                                completed = processed_count
                                status_message = f"Completed: {completed}/{total}, Remaining: {remaining}, Speed: {active_batch_size} per batch"
                                yield f"data: {json.dumps({'type': 'status', 'message': status_message})}\n\n"
                
                # Handle any remaining unprocessed greenlets with force termination
                for idx, (index, row, greenlet) in enumerate(batch_greenlets):
                    if idx in completed_indices:
                        continue  # Already processed
                        
                    # Force wait up to 30 seconds for remaining results, then kill if stuck
                    try:
                        greenlet.join(timeout=30)
                        if not greenlet.ready():
                            app_logger.warning(f"Force killing stuck greenlet for item {index} to prevent hang")
                            greenlet.kill()  # Force terminate stuck greenlets
                    except Exception as e:
                        app_logger.warning(f"Exception handling stuck greenlet for item {index}: {e}")
                        try:
                            greenlet.kill()  # Force terminate on exception
                        except:
                            pass
                    
                    title = row.get('title', "N/A")
                    authors_list = row.get('authors', [])
                    authors_str = ", ".join(authors_list) if authors_list else "Authors Not Found"
                    
                    try:
                        if greenlet.ready() and greenlet.successful():
                            screening_result = greenlet.get(block=False)
                            
                            # Check if greenlet was killed and returned GreenletExit
                            if hasattr(screening_result, '__class__') and 'GreenletExit' in str(type(screening_result)):
                                app_logger.warning(f"Greenlet for item {index} was terminated (GreenletExit)")
                                processing_error_result = {'decision': 'PROCESSING_ERROR', 'reasoning': 'Processing was terminated due to timeout or system constraints'}
                                
                                # Attempt recovery for terminated greenlet
                                app_logger.info(f"Attempting recovery for terminated greenlet on item {index}")
                                from app.utils.utils import handle_processing_error_recovery
                                item_data = {
                                    'abstract': row.get('abstract', ''),
                                    'title': row.get('title', f"Item {index}")
                                }
                                screening_result = handle_processing_error_recovery(
                                    processing_error_result, item_data, llm_provider, llm_model, 
                                    llm_api_key_from_outer_scope, llm_base_url, criteria_prompt
                                )
                            
                            # Ensure screening_result is a dictionary
                            elif not isinstance(screening_result, dict):
                                app_logger.warning(f"Invalid screening result type for item {index}: {type(screening_result)}")
                                screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Invalid result type: {type(screening_result)}'}
                            
                            # Detect network errors
                            elif (screening_result.get('decision') in ['API_HTTP_ERROR_N/A', 'API_TIMEOUT', 'API_ERROR'] and 
                                ('Network error' in str(screening_result.get('reasoning', '')) or 
                                 'ConnectionError' in str(screening_result.get('reasoning', '')) or
                                 'ChunkedEncodingError' in str(screening_result.get('reasoning', '')) or
                                 'timeout' in str(screening_result.get('reasoning', '')).lower())):
                                app_logger.warning(f"Network error detected for item {index}, auto-skipping: {screening_result.get('reasoning', '')}")
                                screening_result = {'decision': 'NETWORK_ERROR', 'reasoning': 'Network error - automatically skipped to prevent hang'}
                            
                            # Detect 429 errors
                            elif (screening_result.get('decision') == 'API_ERROR' and 
                                '429' in str(screening_result.get('reasoning', ''))):
                                batch_429_errors += 1
                        else:
                            # Handle timeout or failure
                            error_msg = str(greenlet.exception) if hasattr(greenlet, 'exception') and greenlet.exception else "Processing timed out"
                            screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': error_msg}
                    except Exception as e:
                        # Handle any unexpected errors during result processing
                        app_logger.error(f"Error processing greenlet result for item {index}: {e}")
                        screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Error processing result: {str(e)}'}
                    
                    # Save result
                    output_data = {
                        'index': index + 1, 
                        'title': title, 
                        'authors': authors_str,
                        'decision': screening_result.get('decision', 'ITEM_ERROR'), 
                        'reasoning': screening_result.get('reasoning', 'Error retrieving result.'),
                        'abstract': row.get('abstract', '')
                    }
                    
                    # Check if result item with same index already exists
                    item_index = output_data['index']
                    existing_item_index = next((i for i, item in enumerate(temp_results_list) 
                                               if item.get('index') == item_index), -1)
                    
                    if existing_item_index >= 0:
                        # If already exists, replace it
                        app_logger.info(f"Replacing existing result with index {item_index}")
                        temp_results_list[existing_item_index] = output_data
                    else:
                        # Otherwise add new item
                        temp_results_list.append(output_data)
                    
                    # Update progress and store UI update event
                    processed_count += 1
                    progress_percentage = int((processed_count / total_entries_to_screen) * 100)
                    
                    progress_event = {
                        'type': 'progress', 
                        'count': processed_count, 
                        'total': total_entries_to_screen,
                        'percentage': progress_percentage, 
                        'current_item_title': title,
                        'decision': screening_result.get('decision', 'ITEM_ERROR'),
                        'item_data': output_data
                    }
                    
                    # Send immediate update
                    yield f"data: {json.dumps(progress_event)}\n\n"
                
                # Adapt parameters based on 429 errors
                if batch_429_errors > 0:
                    rate_limit_errors += batch_429_errors
                    # Reduce batch size and concurrency to reduce API burden
                    active_batch_size = max(5, int(active_batch_size / error_backoff))
                    batch_delay = min(2.0, batch_delay * error_backoff)  # Maximum of 2 seconds
                    app_logger.warning(f"Detected {batch_429_errors} rate limit errors. Adjusting: batch_size={active_batch_size}, delay={batch_delay}s")
                    
                    # Send adjustment info to frontend
                    yield f"data: {json.dumps({'type': 'status', 'message': f'Rate limit detected. Adjusting processing speed (batch:{active_batch_size}, delay:{batch_delay:.2f}s).'})}\n\n"
                elif processed_count > 20 and rate_limit_errors == 0:
                    # If processing a good number of items without errors, try to speed up
                    active_batch_size = min(max_concurrent, active_batch_size + 2)
                    batch_delay = max(0.05, batch_delay * 0.9)  # Minimum of 0.05 seconds
                
                # Delay between batches to avoid API overload
                if to_process and batch_delay > 0:
                    sleep(batch_delay)
                    
                # Send batch completion status update
                if to_process:
                    remaining = len(to_process)
                    total = total_entries_to_screen
                    completed = processed_count
                    status_message = f"Processing: {completed}/{total}, Remaining: {remaining}, Batch size: {active_batch_size}"
                    yield f"data: {json.dumps({'type': 'status', 'message': status_message})}\n\n"
            
            # All items processed, UI updates already sent in real-time
            
            # Sort results by original index
            temp_results_list.sort(key=lambda x: x.get('index', float('inf')))
            
            # Verify all expected items were processed
            if processed_count != total_entries_to_screen:
                app_logger.warning(f"Processed count ({processed_count}) does not match total entries ({total_entries_to_screen}) - may have missed some items")
                
                # Log detailed information about potential missing items
                expected_indices = set(range(1, total_entries_to_screen + 1))  # 1-based indices
                actual_indices = set(item.get('index') for item in temp_results_list if isinstance(item.get('index'), int))
                missing_indices = expected_indices - actual_indices
                
                if missing_indices:
                    app_logger.warning(f"Missing indices: {sorted(list(missing_indices))[:20]}{' and more...' if len(missing_indices) > 20 else ''}")
                    
                    # Try to recover missing items if possible
                    missing_count = 0
                    for index, row in df_for_screening.iterrows():
                        actual_index = index + 1  # 1-based index as used in the UI
                        if actual_index in missing_indices:
                            # Create a basic result for missing items
                            output_data = {
                                'index': actual_index, 
                                'title': row.get('title', "Missing Item"),
                                'authors': ", ".join(row.get('authors', [])) if isinstance(row.get('authors'), list) else "Authors Not Found",
                                'decision': "PROCESSING_ERROR", 
                                'reasoning': "Item was missed during processing. Please review manually.",
                                'abstract': row.get('abstract', '')
                            }
                            temp_results_list.append(output_data)
                            missing_count += 1
                    
                    if missing_count > 0:
                        app_logger.info(f"Added {missing_count} placeholder entries for missing items")
                        # Re-sort after adding missing items
                        temp_results_list.sort(key=lambda x: x.get('index', float('inf')))
            
            app_logger.info(f"PERF SSE: Finished processing {processed_count}/{total_entries_to_screen} items for {original_filename}.")
            if rate_limit_errors > 0:
                app_logger.info(f"Encountered {rate_limit_errors} rate limit errors during processing.")
            
            # Store results and send completion notification
            store_full_screening_session(screening_id, {
                'filename': original_filename, 
                'results': temp_results_list,
                'filter_applied': filter_description
            })
            
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Screening finished.', 'screening_id': screening_id, 'filename': original_filename})}\n\n"
            app_logger.info(f"PERF SSE: Full screening completed for {screening_id}, file {original_filename}. Total time: {time.time() - overall_start_time:.4f} seconds.")
            
        except Exception as e:
            app_logger.exception(f"SSE Server error during full screening processing for {original_filename}")
            error_message_text = f'Server error: {str(e)}'
            yield f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n"
        finally:
            if current_temp_file_path and os.path.exists(current_temp_file_path):
                try:
                    os.unlink(current_temp_file_path)
                    app_logger.info(f"SSE Cleaned up temp file (full screening): {current_temp_file_path}")
                except Exception as e_cleanup:
                    app_logger.warning(f"SSE Could not delete temp file (full screening): {current_temp_file_path} - {e_cleanup}")

    # Pass appropriate parameters to generate_response based on whether we're resuming
    is_resuming = resume_id != '' or request.form.get('resume', '').lower() == 'true'
    return Response(generate_response(line_range_input_val, title_filter_input_val, temp_file_path_full_screen, original_filename_for_session,
                                      criteria_prompt_text_val_full, provider_name_val_full, model_id_val_full, base_url_val_full, api_key_val_full,
                                      is_resuming, resume_from, previously_processed_items),
                   mimetype='text/event-stream')


@app.route('/show_screening_results/<screening_id>', endpoint='show_screening_results') 
def show_screening_results(screening_id):
    session_data = get_full_screening_session(screening_id)
    
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
                           filter_applied=session_data.get('filter_applied', 'all entries'))


# --- New Test Screening SSE Route ---
@app.route('/stream_test_screen_file', methods=['POST'], endpoint='stream_test_screen_file')
def stream_test_screen_file():
    if 'file' not in request.files:
        error_message = {'type': 'error', 'message': 'No file part.'}
        return Response(f"data: {json.dumps(error_message)}\n\n", mimetype='text/event-stream')

    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        error_message = {'type': 'error', 'message': 'No selected file.'}
        return Response(f"data: {json.dumps(error_message)}\n\n", mimetype='text/event-stream')
    if not allowed_file(uploaded_file.filename):
        error_message = {'type': 'error', 'message': 'Invalid file type.'}
        return Response(f"data: {json.dumps(error_message)}\n\n", mimetype='text/event-stream')

    try:
        sample_size_str_val = request.form.get('sample_size', '10') 
        sample_size_val = int(sample_size_str_val)
        sample_size_val = max(5, min(9999, sample_size_val)) 
    except ValueError: 
        sample_size_val = 10
    
    line_range_input_val = request.form.get('line_range_filter', '').strip()
    title_filter_input_val = request.form.get('title_text_filter', '').strip()

    criteria_prompt_text_val_full = get_screening_criteria()
    current_llm_config_data_val_full = get_current_llm_config(session)
    provider_name_val_full = current_llm_config_data_val_full['provider_name']
    model_id_val_full = current_llm_config_data_val_full['model_id']
    base_url_val_full = get_base_url_for_provider(provider_name_val_full)
    provider_info_val_full = get_llm_providers_info().get(provider_name_val_full, {})
    session_key_name_val_full = provider_info_val_full.get("api_key_session_key")
    api_key_val_full = session.get(session_key_name_val_full) if session_key_name_val_full else None
    
    original_filename_for_log = uploaded_file.filename
    temp_file_path_for_generator = os.path.join(UPLOAD_FOLDER, f"temp_test_sse_{uuid.uuid4()}.ris")

    try:
        uploaded_file.save(temp_file_path_for_generator)
        app_logger.info(f"SSE Test screening: Uploaded file saved to temporary path: {temp_file_path_for_generator}")
    except Exception as e_save:
        app_logger.error(f"SSE Test screening: Failed to save uploaded file initially: {e_save}")
        return Response(f"data: {json.dumps({'type': 'error', 'message': f'Failed to save uploaded file: {e_save}'})}\n\n", mimetype='text/event-stream')

    def quick_start_response_generator(sample_size_param, line_range_filter_from_form, title_filter_from_form, saved_temp_file_path, 
                                     criteria_prompt_param, llm_provider_param, llm_model_param, llm_base_url_param, llm_api_key_from_outer_scope):
        # Import gevent.sleep
        from gevent import sleep
        
        overall_start_time = time.time()
        app_logger.info(f"PERF SSE Test: quick_start_response_generator started for {original_filename_for_log}.")
        current_temp_file_path = saved_temp_file_path
        
        yield f"data: {json.dumps({'type': 'init', 'message': 'Processing upload, please wait...'})}\n\n"
        
        try:
            current_sample_size = sample_size_param
            line_range_input = line_range_filter_from_form
            title_filter_input = title_filter_from_form
        
            with open(current_temp_file_path, 'rb') as f_stream:
                df = load_literature_ris(f_stream)
            
            if df is None or df.empty:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to load RIS or file empty.'})}\n\n"
                return
            if 'abstract' not in df.columns:
                yield f"data: {json.dumps({'type': 'error', 'message': 'RIS missing abstract column.'})}\n\n"
                return
                
            df['title'] = df.get('title', pd.Series(["Title Not Found"] * len(df))).fillna("Title Not Found")
            df['authors'] = df.get('authors', pd.Series([[] for _ in range(len(df))]))
            df['authors'] = df['authors'].apply(lambda x: x if isinstance(x, list) else [])

            df_for_screening = df.copy()
            original_df_count = len(df)
            filter_description = "all entries"

            if title_filter_input:
                df_for_screening = df_for_screening[df_for_screening['title'].str.contains(title_filter_input, case=False, na=False)]
                filter_description = f"entries matching title '{title_filter_input}'"
                if df_for_screening.empty:
                    message_text = f'No articles found matching title: "{title_filter_input}"'
                    yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
                    return
            elif line_range_input:
                try:
                    start_idx, end_idx = parse_line_range(line_range_input, original_df_count)
                    if start_idx >= end_idx:
                        message_text = f'The range "{line_range_input}" is invalid or results in no articles.'
                        yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
                        return
                    df_for_screening = df_for_screening.iloc[start_idx:end_idx]
                    filter_description = f"entries in 1-based range [{start_idx + 1}-{end_idx}]"
                    if df_for_screening.empty:
                        message_text = f'The range "{line_range_input}" resulted in no articles to screen.'
                        yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
                        return
                except ValueError as e:
                    message_text = f'Invalid range format for "{line_range_input}": {str(e)}'
                    yield f"data: {json.dumps({'type': 'error', 'message': message_text})}\n\n"
                    return

            if df_for_screening.empty and (title_filter_input or line_range_input):
                yield f"data: {json.dumps({'type': 'error', 'message': 'No articles found after applying filters to sample from.'})}\n\n"
                return

            sample_df = df_for_screening.head(min(current_sample_size, len(df_for_screening)))
            actual_sample_size = len(sample_df)

            if actual_sample_size == 0:
                yield f"data: {json.dumps({'type': 'error', 'message': 'No entries found in the file to sample (after filters if any).'})}\n\n"
                return

            if not llm_api_key_from_outer_scope:
                message_text = f'API Key for {llm_provider_param} must be provided.'
                yield f"data: {json.dumps({'type': 'error', 'message': message_text, 'needs_config': True})}\n\n"
                return

            session_id = str(uuid.uuid4())
            store_test_session(session_id, {
                'file_name': original_filename_for_log, 
                'sample_size': actual_sample_size, 
                'test_items_data': [],
                'filter_applied': filter_description 
            })

            yield f"data: {json.dumps({'type': 'start', 'total': actual_sample_size, 'filter_info': filter_description})}\n\n"
            app_logger.info(f"PERF SSE Test: Processing {actual_sample_size} sample items for file {original_filename_for_log} using smart batch processing.")

            # Smart batch processing system
            # Adaptive parameters - optimize for speed and real-time UI updates
            active_batch_size = min(20, actual_sample_size)  # Larger batch size for better performance
            max_concurrent = 30  # Higher concurrency for faster processing
            batch_delay = 0.0  # No delay between batches
            error_backoff = 1.5  # Error backoff multiplier
            
            # Track 429 errors
            rate_limit_errors = 0
            
            # Prepare all items to process
            to_process = []
            for index, row in sample_df.iterrows():
                to_process.append((index, row))
            
            # Track processing status
            processed_count = 0
            temp_results_list = []
            
            # Use immediate update method, no queue or timer needed
            
            # Process items in batches
            while to_process:
                # Extract current batch
                current_batch = to_process[:active_batch_size]
                to_process = to_process[active_batch_size:]
                
                # Launch greenlets for current batch
                batch_greenlets = []
                batch_429_errors = 0  # Rate limit error count for this batch
                
                for index, row in current_batch:
                    abstract = row.get('abstract')
                    greenlet = spawn(_perform_screening_on_abstract,
                                   abstract, criteria_prompt_param,
                                   llm_provider_param, llm_model_param, 
                                   llm_api_key_from_outer_scope, llm_base_url_param, index)
                    batch_greenlets.append((index, row, greenlet))
                
                # Optimize: Use reasonable timeout for DeepSeek reasoner model
                max_wait_time = 90  # 90 seconds timeout - DeepSeek reasoner needs 20-40s per call
                check_interval = 0.5  # Check every 500ms for stability
                checks_completed = 0
                max_checks = int(max_wait_time / check_interval)
                
                completed_indices = set()
                
                # More frequent checks for results to provide immediate updates
                while checks_completed < max_checks and len(completed_indices) < len(batch_greenlets):
                    # Brief wait
                    sleep(check_interval)
                    checks_completed += 1
                    
                    # Check for completed greenlets and send immediate updates
                    for idx, (index, row, greenlet) in enumerate(batch_greenlets):
                        if idx in completed_indices:
                            continue  # Already processed this greenlet
                            
                        if greenlet.ready():
                            completed_indices.add(idx)
                            
                            title = row.get('title', "N/A")
                            abstract_text = row.get('abstract', '')
                            authors_list = row.get('authors', [])
                            authors_str = ", ".join(authors_list) if authors_list else "Authors Not Found"
                            
                            # Generate unique ID for test item
                            item_id = str(uuid.uuid4())
                            
                            # Process result with enhanced error handling
                            try:
                                if greenlet.successful():
                                    screening_result = greenlet.get(block=False)
                                    
                                    # Check if greenlet was killed and returned GreenletExit
                                    if hasattr(screening_result, '__class__') and 'GreenletExit' in str(type(screening_result)):
                                        app_logger.warning(f"Test greenlet for item {index} was terminated (GreenletExit)")
                                        screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': 'Processing was terminated due to timeout or system constraints'}
                                    
                                    # Ensure screening_result is a dictionary
                                    elif not isinstance(screening_result, dict):
                                        app_logger.warning(f"Invalid test screening result type for item {index}: {type(screening_result)}")
                                        screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Invalid result type: {type(screening_result)}'}
                                    
                                    # Fast detection of network errors - auto skip to prevent hang
                                    elif (screening_result.get('decision') in ['API_HTTP_ERROR_N/A', 'API_TIMEOUT', 'API_ERROR'] and 
                                        ('Network error' in str(screening_result.get('reasoning', '')) or 
                                         'ConnectionError' in str(screening_result.get('reasoning', '')) or
                                         'ChunkedEncodingError' in str(screening_result.get('reasoning', '')) or
                                         'timeout' in str(screening_result.get('reasoning', '')).lower())):
                                        app_logger.warning(f"Network error detected for test item {index}, auto-skipping: {screening_result.get('reasoning', '')}")
                                        screening_result = {'decision': 'NETWORK_ERROR', 'reasoning': 'Network error - automatically skipped to prevent hang'}
                                    
                                    # Detect 429 errors
                                    elif (screening_result.get('decision') == 'API_ERROR' and 
                                        '429' in str(screening_result.get('reasoning', ''))):
                                        batch_429_errors += 1
                                else:
                                    # Handle timeout or failure
                                    error_msg = str(greenlet.exception) if greenlet.exception else "Processing error"
                                    screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': error_msg}
                            except Exception as e:
                                # Handle any unexpected errors during result processing
                                app_logger.error(f"Error processing test greenlet result for item {index}: {e}")
                                screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Error processing result: {str(e)}'}
                            
                            # Prepare test item data
                            test_item_template_data = {
                                'id': item_id, 
                                'original_index': index, 
                                'title': title,
                                'authors': authors_str, 
                                'abstract': abstract_text,
                                'ai_decision': screening_result.get('decision', 'ITEM_ERROR'), 
                                'ai_reasoning': screening_result.get('reasoning', 'Error retrieving result.')
                            }
                            temp_results_list.append(test_item_template_data)
                            
                            # Update progress and send immediate notification
                            processed_count += 1
                            
                            # Calculate progress percentage
                            progress_percentage = int((processed_count / actual_sample_size) * 100)
                            
                            # Create progress update event
                            progress_event_data = {
                                'type': 'progress', 
                                'count': processed_count, 
                                'total': actual_sample_size,
                                'percentage': progress_percentage, 
                                'current_item_title': title,
                                'decision': screening_result.get('decision', 'ITEM_ERROR')
                            }
                            
                            # Send immediate update for real-time feedback
                            yield f"data: {json.dumps(progress_event_data)}\n\n"
                            
                            # Send status updates for every item processed for real-time feedback
                            yield f"data: {json.dumps({'type': 'status', 'message': f'Processed: {processed_count}/{actual_sample_size}, Remaining: {len(to_process) + (len(batch_greenlets) - len(completed_indices))}, Speed: {active_batch_size} per batch'})}\n\n"
                
                # Handle any remaining unprocessed greenlets (most should have been handled in loop above)
                for idx, (index, row, greenlet) in enumerate(batch_greenlets):
                    if idx in completed_indices:
                        continue  # Already processed this greenlet
                        
                    # Force wait up to 30 seconds to get remaining results, then kill if stuck
                    try:
                        greenlet.join(timeout=30)
                        if not greenlet.ready():
                            app_logger.warning(f"Force killing stuck test greenlet for item {index} to prevent hang")
                            greenlet.kill()  # Force terminate stuck greenlets
                    except Exception as e:
                        app_logger.warning(f"Exception handling stuck test greenlet for item {index}: {e}")
                        try:
                            greenlet.kill()  # Force terminate on exception
                        except:
                            pass
                    
                    title = row.get('title', "N/A")
                    abstract_text = row.get('abstract', '')
                    authors_list = row.get('authors', [])
                    authors_str = ", ".join(authors_list) if authors_list else "Authors Not Found"
                    
                    # Generate unique ID for test item
                    item_id = str(uuid.uuid4())
                    
                    try:
                        if greenlet.ready() and greenlet.successful():
                            screening_result = greenlet.get(block=False)
                            
                            # Check if greenlet was killed and returned GreenletExit
                            if hasattr(screening_result, '__class__') and 'GreenletExit' in str(type(screening_result)):
                                app_logger.warning(f"Test greenlet for item {index} was terminated (GreenletExit)")
                                screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': 'Processing was terminated due to timeout or system constraints'}
                            
                            # Ensure screening_result is a dictionary
                            elif not isinstance(screening_result, dict):
                                app_logger.warning(f"Invalid test screening result type for item {index}: {type(screening_result)}")
                                screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Invalid result type: {type(screening_result)}'}
                            
                            # Detect network errors
                            elif (screening_result.get('decision') in ['API_HTTP_ERROR_N/A', 'API_TIMEOUT', 'API_ERROR'] and 
                                ('Network error' in str(screening_result.get('reasoning', '')) or 
                                 'ConnectionError' in str(screening_result.get('reasoning', '')) or
                                 'ChunkedEncodingError' in str(screening_result.get('reasoning', '')) or
                                 'timeout' in str(screening_result.get('reasoning', '')).lower())):
                                app_logger.warning(f"Network error detected for test item {index}, auto-skipping: {screening_result.get('reasoning', '')}")
                                screening_result = {'decision': 'NETWORK_ERROR', 'reasoning': 'Network error - automatically skipped to prevent hang'}
                            
                            # Detect 429 errors
                            elif (screening_result.get('decision') == 'API_ERROR' and 
                                '429' in str(screening_result.get('reasoning', ''))):
                                batch_429_errors += 1
                        else:
                            # Handle timeout or failure
                            error_msg = str(greenlet.exception) if hasattr(greenlet, 'exception') and greenlet.exception else "Processing timed out"
                            screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': error_msg}
                    except Exception as e:
                        # Handle any unexpected errors during result processing
                        app_logger.error(f"Error processing test greenlet result for item {index}: {e}")
                        screening_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Error processing result: {str(e)}'}
                    
                    # Prepare test item data
                    test_item_template_data = {
                        'id': item_id, 
                        'original_index': index, 
                        'title': title,
                        'authors': authors_str, 
                        'abstract': abstract_text,
                        'ai_decision': screening_result.get('decision', 'ITEM_ERROR'), 
                        'ai_reasoning': screening_result.get('reasoning', 'Error retrieving result.')
                    }
                    temp_results_list.append(test_item_template_data)
                    
                    # Update progress and send notification
                    processed_count += 1
                    
                    # Calculate progress percentage
                    progress_percentage = int((processed_count / actual_sample_size) * 100)
                    
                    # Create progress update event
                    progress_event_data = {
                        'type': 'progress', 
                        'count': processed_count, 
                        'total': actual_sample_size,
                        'percentage': progress_percentage, 
                        'current_item_title': title,
                        'decision': screening_result.get('decision', 'ITEM_ERROR')
                    }
                    
                    # Send immediate update for real-time feedback
                    yield f"data: {json.dumps(progress_event_data)}\n\n"
                
                # Adjust parameters based on 429 errors
                if batch_429_errors > 0:
                    rate_limit_errors += batch_429_errors
                    # Reduce batch size and concurrency to reduce API burden
                    active_batch_size = max(3, int(active_batch_size / error_backoff))
                    batch_delay = min(2.0, batch_delay * error_backoff)  # Maximum of 2 seconds
                    app_logger.warning(f"Test: Detected {batch_429_errors} rate limit errors. Adjusting: batch_size={active_batch_size}, delay={batch_delay}s")
                    
                    # Send rate limit notification to frontend
                    yield f"data: {json.dumps({'type': 'status', 'message': f'Test set: Rate limit detected. Adjusting processing speed (batch:{active_batch_size}, delay:{batch_delay:.2f}s).'})}\n\n"
                elif processed_count > 10 and rate_limit_errors == 0:
                    # If processing a number of items without errors, try to speed up
                    active_batch_size = min(max_concurrent, active_batch_size + 2)
                    batch_delay = max(0.05, batch_delay * 0.9)  # Minimum of 0.05 seconds
                
                # Delay between batches to avoid API overload
                if to_process and batch_delay > 0:
                    sleep(batch_delay)
                
                # Send batch completion status update
                if to_process:
                    remaining = len(to_process)
                    total = actual_sample_size
                    completed = processed_count
                    status_message = f"Test set: Completed: {completed}/{total}, Remaining: {remaining}, Speed: {active_batch_size} per batch"
                    yield f"data: {json.dumps({'type': 'status', 'message': status_message})}\n\n"
            
            # All items processed, UI updates sent in real-time
            
            # Sort results by original index
            temp_results_list.sort(key=lambda x: x.get('original_index', float('inf')))
            
            app_logger.info(f"PERF SSE Test: Finished processing {processed_count}/{actual_sample_size} items for {original_filename_for_log}.")
            if rate_limit_errors > 0:
                app_logger.info(f"Test: Encountered {rate_limit_errors} rate limit errors during processing.")
            
            # Update session data and send completion notification
            current_session_data = get_test_session(session_id)
            if current_session_data:
                current_session_data['test_items_data'] = temp_results_list
                store_test_session(session_id, current_session_data)
            else:
                app_logger.warning(f"SSE Test: Session {session_id} disappeared before storing test results for {original_filename_for_log}.")

            complete_data = {'type': 'complete', 'message': 'Test screening finished.', 'session_id': session_id, 'filename': original_filename_for_log}
            yield f"data: {json.dumps(complete_data)}\n\n"
            app_logger.info(f"PERF SSE Test: Test screening completed for {session_id}, file {original_filename_for_log}. Total time: {time.time() - overall_start_time:.4f} seconds.")
            
        except Exception as e: 
            app_logger.exception(f"SSE Test Server error during test streaming processing for {original_filename_for_log}")
            error_message_text = f'Server error: {str(e)}'
            yield f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n"
        finally:
            if current_temp_file_path and os.path.exists(current_temp_file_path):
                try:
                    os.unlink(current_temp_file_path)
                    app_logger.info(f"SSE Test Cleaned up temp file: {current_temp_file_path}")
                except Exception as e_cleanup:
                    app_logger.warning(f"SSE Test Could not delete temp file: {current_temp_file_path} - {e_cleanup}")
    
    return Response(quick_start_response_generator(sample_size_val, line_range_input_val, title_filter_input_val, temp_file_path_for_generator,
                                                 criteria_prompt_text_val_full, provider_name_val_full, model_id_val_full, base_url_val_full, api_key_val_full), 
                  mimetype='text/event-stream')


@app.route('/show_test_results/<session_id>', endpoint='show_test_results')
def show_test_results(session_id):
    session_data = get_test_session(session_id)
    
    if not session_data:
        flash('Test session not found or expired. Please start a new test.', 'error')
        return redirect(url_for('abstract_screening_page'))

    test_items = session_data.get('test_items_data')
    
    if not test_items: # If empty list or key missing
         flash('No test items found in session for display.', 'warning')
         return redirect(url_for('abstract_screening_page'))

    current_year = datetime.datetime.now().year
    return render_template('test_results.html',
                           test_items=test_items,
                           session_id=session_id,
                           current_year=current_year,
                           filter_applied=session_data.get('filter_applied', 'all entries'))


# --- New Download Route --- 
@app.route('/download_results/<screening_id>/<format>', endpoint='download_results')
def download_results(screening_id, format):
    session_data = get_full_screening_session(screening_id)
    
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
            
            # 添加错误处理和恢复机制
            if screening_result and isinstance(screening_result, dict):
                decision = screening_result.get('label', 'ERROR')
                reasoning = screening_result.get('justification', 'API call failed or returned invalid data.')
                
                # 检查是否需要恢复
                if decision in ['API_TIMEOUT', 'API_HTTP_ERROR_N/A', 'SCRIPT_ERROR']:
                    app_logger.warning(f"PDF screening error detected: {decision} - {reasoning}")
                    
                    # 尝试恢复
                    from app.utils.utils import handle_processing_error_recovery
                    error_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'PDF screening failed: {reasoning}'}
                    item_data = {
                        'abstract': full_text[:2000],  # 使用前2000字符作为摘要
                        'title': original_filename
                    }
                    
                    recovery_result = handle_processing_error_recovery(
                        error_result, item_data, provider_name, model_id, api_key, base_url, criteria_full_text
                    )
                    
                    if recovery_result.get('decision') in ['INCLUDE', 'EXCLUDE', 'MAYBE']:
                        app_logger.info(f"PDF screening recovered successfully: {recovery_result.get('decision')}")
                        decision = recovery_result.get('decision')
                        reasoning = f"[RECOVERED] {recovery_result.get('reasoning')}"
                    else:
                        app_logger.warning(f"PDF screening recovery failed: {recovery_result.get('reasoning')}")
                        decision = recovery_result.get('decision', 'RECOVERY_FAILED')
                        reasoning = recovery_result.get('reasoning', 'Recovery attempt failed')
            else:
                decision = 'API_ERROR'
                reasoning = 'API call returned invalid response format'
            
            pdf_screening_results[pdf_screening_id] = {
                'filename': original_filename, # Original filename for display
                'saved_pdf_path': pdf_save_path, # Store the path to the saved PDF
                'decision': decision,
                'reasoning': reasoning,
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
            flash(f"An error occurred during data extraction for {filename if 'filename' in locals() else 'the uploaded PDF'}: {e}", "error")
            app_logger.exception(f"An error occurred during data extraction for PDF: {filename if 'filename' in locals() else 'N/A'}")
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
        error_message_text = 'No PDF files uploaded or all files are empty.'
        return Response(f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n", mimetype='text/event-stream')

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
        error_message_text = 'No valid PDF files found in upload.'
        return Response(f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n", mimetype='text/event-stream')

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
            error_message_text = f'No PDF files found matching filename filter: "{title_filter_input}"'
            return Response(
                f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n",
                mimetype='text/event-stream'
            )
            
    if not applied_title_filter and order_filter_input: 
        try:
            num_items_for_order_filter = len(files_to_process_manifest)
            start_idx_0_based, end_idx_0_based_exclusive = parse_line_range(order_filter_input, num_items_for_order_filter)
            
            if start_idx_0_based >= end_idx_0_based_exclusive:
                app_logger.info(f"Batch PDF Stream: Order filter range '{order_filter_input}' is invalid or results in no files.")
                error_message_text = f'The order filter range "{order_filter_input}" is invalid or results in no files.' # Corrected
                return Response(f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n", mimetype='text/event-stream')

            files_to_process_manifest = files_to_process_manifest[start_idx_0_based:end_idx_0_based_exclusive]
            filter_description = f"files by order range [{start_idx_0_based+1}-{end_idx_0_based_exclusive}]"
            
            if not files_to_process_manifest:
                app_logger.info(f"Batch PDF Stream: No files matched order filter '{order_filter_input}'.")
                error_message_text = 'No PDF files found for the specified order range.' # Corrected
                return Response(f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n", mimetype='text/event-stream')
        
        except ValueError as e:
            app_logger.warning(f"Batch PDF Stream: Invalid order filter format '{order_filter_input}': {e}")
            error_message_text = f'Invalid format for order filter "{order_filter_input}": {str(e)}' # Corrected
            return Response(f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n", mimetype='text/event-stream')

    total_files_to_process = len(files_to_process_manifest)
    if total_files_to_process == 0 and (title_filter_input or order_filter_input):
        app_logger.info("Batch PDF Stream: No files selected for processing after filters.")
        error_message_text = 'No PDF files selected for processing after applying filters.' # Corrected
        return Response(f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n", mimetype='text/event-stream')

    app_logger.info(f"Batch PDF Stream: {total_files_to_process} file(s) selected. Filter applied: {filter_description}")
    selected_filenames_log = [item['original_filename'] for item in files_to_process_manifest]
    app_logger.info(f"Batch PDF Stream: Selected files for processing: {selected_filenames_log}")

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
            def sse_error_gen():
                error_message_text = f'API Key for {llm_provider_name} must be provided via configuration.' # Corrected
                yield f"data: {json.dumps({'type': 'error', 'message': error_message_text, 'needs_config': True})}\n\n"
            return Response(sse_error_gen(), mimetype='text/event-stream')
    except Exception as e_config:
        app_logger.exception("Batch PDF Stream: Error fetching LLM/Criteria configuration.")
        def sse_config_error_gen():
            error_message_text = f'Error fetching LLM/Criteria configuration: {str(e_config)}' # Corrected
            yield f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n"
        return Response(sse_config_error_gen(), mimetype='text/event-stream')
    
    upload_folder_path = app.config['UPLOAD_FOLDER']
    files_ready_for_threads = []
    for item_manifest in files_to_process_manifest: # item_manifest already contains original_index
        file_storage = item_manifest['file_storage']
        original_filename = item_manifest['original_filename']
        try:
            file_storage.seek(0)
            temp_file_id = str(uuid.uuid4())
            processing_filename = f"batch_processing_{temp_file_id}_{original_filename}"
            processing_file_path = os.path.join(upload_folder_path, processing_filename)
            file_storage.save(processing_file_path)
            app_logger.info(f"Batch PDF: Pre-saved '{original_filename}' to '{processing_file_path}' for thread processing.")
            files_ready_for_threads.append({
                'original_index': item_manifest['original_index'], # Pass along the original_index
                'original_filename': original_filename,
                'processing_file_path': processing_file_path
            })
        except Exception as e_save:
            app_logger.error(f"Batch PDF: Failed to pre-save file '{original_filename}' for processing: {e_save}")
            # Consider how to handle files that fail to pre-save: skip or report error for them specifically.
            # For now, they are just not added to files_ready_for_threads.
            pass 
            
    if not files_ready_for_threads:
        app_logger.warning("Batch PDF Stream: No files were successfully pre-saved for processing.")
        def sse_presave_error_gen(): 
            error_message_text = 'Failed to prepare any files for batch processing.' # Corrected
            yield f"data: {json.dumps({'type': 'error', 'message': error_message_text})}\n\n"
        return Response(sse_presave_error_gen(), mimetype='text/event-stream')

    total_files_to_process = len(files_ready_for_threads) 
    def generate_processing_progress(): # Inner generator function
        from gevent import sleep
        yield f"data: {json.dumps({'type': 'start', 'total_uploaded': len(initial_manifest), 'total_to_process': total_files_to_process, 'filter_info': filter_description})}\n\n"
        
        processed_files_results = []
        
        if not files_ready_for_threads:
            app_logger.warning("Batch PDF SSE: No files ready for processing in generator.")
            yield f"data: {json.dumps({'type': 'complete', 'message': 'No files to process.', 'batch_session_id': None})}\n\n"
            return

        app_logger.info(f"Batch PDF SSE: Spawning greenlets for {total_files_to_process} PDF files.")
        greenlets_info = []

        for item_manifest_with_path in files_ready_for_threads:
            g = spawn(_perform_batch_pdf_screening_for_file, 
                      item_manifest_with_path, 
                      criteria_prompt_text, 
                      llm_provider_name, 
                      llm_model_id, 
                      llm_api_key, 
                      llm_base_url)
            greenlets_info.append({'greenlet': g, 'manifest': item_manifest_with_path})

        # Real-time progress monitoring instead of waiting for all to complete
        processed_count = 0
        completed_greenlets = set()
        
        app_logger.info(f"Batch PDF SSE: Starting real-time monitoring of {len(greenlets_info)} greenlets.")
        
        # Monitor greenlets in real time
        while processed_count < total_files_to_process:
            sleep(0.5)  # Check every 500ms for completed tasks
            
            for i, info in enumerate(greenlets_info):
                if i in completed_greenlets:
                    continue  # Skip already processed greenlets
                    
                glet = info['greenlet']
                completed_item_manifest = info['manifest']
                original_filename_for_log = completed_item_manifest['original_filename']
                
                if glet.ready():  # Check if this greenlet has completed
                    completed_greenlets.add(i)
                    screening_result = None
                    
                    try:
                        if glet.successful():
                            screening_result = glet.get(block=False)
                            
                            # Check if greenlet was killed and returned GreenletExit
                            if hasattr(screening_result, '__class__') and 'GreenletExit' in str(type(screening_result)):
                                app_logger.warning(f"Batch PDF greenlet for {original_filename_for_log} was terminated (GreenletExit)")
                                screening_result = {
                                    'original_index': completed_item_manifest['original_index'],
                                    'filename': original_filename_for_log, 
                                    'title_for_display': original_filename_for_log,
                                    'decision': 'PROCESSING_ERROR',
                                    'reasoning': 'Processing was terminated due to timeout or system constraints'
                                }
                            
                            # Ensure screening_result is a dictionary
                            elif not isinstance(screening_result, dict):
                                app_logger.warning(f"Invalid batch PDF screening result type for {original_filename_for_log}: {type(screening_result)}")
                                screening_result = {
                                    'original_index': completed_item_manifest['original_index'],
                                    'filename': original_filename_for_log, 
                                    'title_for_display': original_filename_for_log,
                                    'decision': 'PROCESSING_ERROR',
                                    'reasoning': f'Invalid result type: {type(screening_result)}'
                                }
                            
                            # Fast detection of network errors - auto skip to prevent hang
                            elif (screening_result.get('decision') in ['API_HTTP_ERROR_N/A', 'API_TIMEOUT', 'API_ERROR'] and 
                                ('Network error' in str(screening_result.get('reasoning', '')) or 
                                 'ConnectionError' in str(screening_result.get('reasoning', '')) or
                                 'ChunkedEncodingError' in str(screening_result.get('reasoning', '')) or
                                 'timeout' in str(screening_result.get('reasoning', '')).lower())):
                                app_logger.warning(f"Network error detected for batch PDF {original_filename_for_log}, auto-skipping: {screening_result.get('reasoning', '')}")
                                screening_result['decision'] = 'NETWORK_ERROR'
                                screening_result['reasoning'] = 'Network error - automatically skipped to prevent hang'
                        else:
                            app_logger.error(f"Batch PDF SSE: Unhandled exception in greenlet for {original_filename_for_log}: {glet.exception}")
                            screening_result = {
                                'original_index': completed_item_manifest['original_index'],
                                'filename': original_filename_for_log, 
                                'title_for_display': original_filename_for_log,
                                'decision': 'GREENLET_ERROR',
                                'reasoning': str(glet.exception)
                            }
                    except Exception as e_future:
                        app_logger.error(f"Batch PDF SSE: Exception processing greenlet result for {original_filename_for_log}: {e_future}")
                        screening_result = {
                            'original_index': completed_item_manifest['original_index'],
                            'filename': original_filename_for_log, 
                            'title_for_display': original_filename_for_log,
                            'decision': 'PROCESSING_ERROR',
                            'reasoning': str(e_future)
                        }
                    
                    if screening_result:
                        processed_files_results.append(screening_result)
                    else:
                        app_logger.error(f"Batch PDF SSE: No screening_result obtained for {original_filename_for_log}")
                        processed_files_results.append({
                            'original_index': completed_item_manifest['original_index'],
                            'filename': original_filename_for_log, 
                            'title_for_display': original_filename_for_log,
                            'decision': 'UNKNOWN_ERROR',
                            'reasoning': 'Result was not captured from greenlet processing.'
                        })
                    
                    processed_count += 1
                    
                    # Send real-time progress update
                    progress_percentage = int((processed_count / total_files_to_process) * 100)
                    yield f"data: {json.dumps({'type': 'progress', 'count': processed_count, 'total_to_process': total_files_to_process, 'percentage': progress_percentage, 'current_file_name': screening_result.get('filename', original_filename_for_log), 'decision': screening_result.get('decision', 'ERROR')})}\n\n"
                    
                    app_logger.info(f"Batch PDF SSE: Completed {processed_count}/{total_files_to_process}: {original_filename_for_log} - {screening_result.get('decision', 'ERROR')}")
        
        # Handle any remaining incomplete greenlets (timeout case)
        remaining_timeout = 10  # Additional 10 seconds for any stragglers
        app_logger.info(f"Batch PDF SSE: All tasks completed or checking for stragglers with {remaining_timeout}s timeout")
        
        for i, info in enumerate(greenlets_info):
            if i not in completed_greenlets:
                glet = info['greenlet']
                completed_item_manifest = info['manifest']
                original_filename_for_log = completed_item_manifest['original_filename']
                
                try:
                    # Give remaining tasks a short time to complete
                    glet.join(timeout=remaining_timeout)
                    
                    if glet.ready() and glet.successful():
                        screening_result = glet.get(block=False)
                        
                        # Check if greenlet was killed and returned GreenletExit
                        if hasattr(screening_result, '__class__') and 'GreenletExit' in str(type(screening_result)):
                            app_logger.warning(f"Late batch PDF greenlet for {original_filename_for_log} was terminated (GreenletExit)")
                            screening_result = {
                                'original_index': completed_item_manifest['original_index'],
                                'filename': original_filename_for_log,
                                'title_for_display': original_filename_for_log,
                                'decision': 'PROCESSING_ERROR',
                                'reasoning': 'Processing was terminated due to timeout or system constraints'
                            }
                        
                        # Ensure screening_result is a dictionary
                        elif not isinstance(screening_result, dict):
                            app_logger.warning(f"Invalid late batch PDF screening result type for {original_filename_for_log}: {type(screening_result)}")
                            screening_result = {
                                'original_index': completed_item_manifest['original_index'],
                                'filename': original_filename_for_log,
                                'title_for_display': original_filename_for_log,
                                'decision': 'PROCESSING_ERROR',
                                'reasoning': f'Invalid result type: {type(screening_result)}'
                            }
                        
                        processed_files_results.append(screening_result)
                        app_logger.info(f"Batch PDF SSE: Late completion for {original_filename_for_log}")
                    else:
                        # Handle timeout or error for remaining tasks - force kill stuck greenlets
                        if not glet.ready():
                            app_logger.warning(f"Force killing stuck batch PDF greenlet for {original_filename_for_log} to prevent hang")
                            try:
                                glet.kill()  # Force terminate stuck greenlets
                            except:
                                pass
                        
                        app_logger.warning(f"Batch PDF SSE: Greenlet for {original_filename_for_log} timed out or failed")
                        timeout_result = {
                            'original_index': completed_item_manifest['original_index'],
                            'filename': original_filename_for_log,
                            'title_for_display': original_filename_for_log,
                            'decision': 'TIMEOUT_ERROR', 
                            'reasoning': 'Processing timed out.'
                        }
                        processed_files_results.append(timeout_result)
                except Exception as e_timeout:
                    app_logger.error(f"Batch PDF SSE: Error handling timeout for {original_filename_for_log}: {e_timeout}")

        processed_files_results.sort(key=lambda x: x.get('original_index', float('inf')))
        
        batch_session_id = str(uuid.uuid4())
        if processed_files_results: 
            store_full_screening_session(batch_session_id, { 
                'filename': f"Batch PDF Results ({len(processed_files_results)} of {total_files_to_process} processed)", 
                'filter_applied': filter_description,
                'results': processed_files_results,
                'is_batch_pdf_result': True 
            })
            app_logger.info(f"Batch PDF SSE: Stored {len(processed_files_results)} results under batch ID {batch_session_id}")
        else:
            app_logger.warning("Batch PDF SSE: No results were processed or collected.")
            
        yield f"data: {json.dumps({'type': 'complete', 'message': 'Batch PDF processing finished.', 'batch_session_id': batch_session_id if processed_files_results else None})}\n\n"
        app_logger.info(f"Batch PDF SSE: Processing SSE finished. Batch ID: {batch_session_id if processed_files_results else 'N/A'}")

    return Response(generate_processing_progress(), mimetype='text/event-stream')

# --- END NEW Batch PDF Results Route ---


# --- NEW Helper for processing a single PDF in batch ---
def _perform_batch_pdf_screening_for_file(item_manifest_with_path_and_index, criteria_prompt_text, llm_provider_name, llm_model_id, llm_api_key, llm_base_url):
    original_filename = item_manifest_with_path_and_index['original_filename']
    processing_file_path = item_manifest_with_path_and_index['processing_file_path']
    original_index_from_manifest = item_manifest_with_path_and_index['original_index'] # Get original_index
    
    display_title = original_filename 
    try:
        app_logger.info(f"Batch PDF Thread: Processing '{original_filename}' from path '{processing_file_path}'.")
        
        # Attempt to get title from PDF metadata using PyMuPDF
        try:
            doc = fitz.open(processing_file_path)
            metadata = doc.metadata
            pdf_title_from_meta = metadata.get('title')
            if pdf_title_from_meta and isinstance(pdf_title_from_meta, str) and pdf_title_from_meta.strip():
                display_title = pdf_title_from_meta.strip()
                app_logger.info(f"Batch PDF Thread: Extracted title '{display_title}' from metadata for '{original_filename}'.")
            else:
                app_logger.info(f"Batch PDF Thread: No usable title in metadata for '{original_filename}', using filename as display title.")
            doc.close()
        except Exception as e_meta:
            app_logger.warning(f"Batch PDF Thread: Could not read metadata for title from '{original_filename}': {e_meta}. Using filename as display title.")
            # display_title remains original_filename in case of error

        with open(processing_file_path, 'rb') as saved_file_stream:
            full_text = extract_text_from_pdf(saved_file_stream, ocr_language='eng') 
        
        if full_text is None:
            app_logger.error(f"Batch PDF Thread: Failed to extract text from '{original_filename}'.")
            return {'original_index': original_index_from_manifest, 'filename': original_filename, 'title_for_display': display_title, 'decision': 'TEXT_EXTRACT_ERROR', 'reasoning': 'Failed to extract text from PDF.'}
        
        prompt_data = construct_llm_prompt(full_text, criteria_prompt_text)
        if not prompt_data:
            app_logger.error(f"Batch PDF Thread: Failed to construct LLM prompt for '{original_filename}'.")
            return {'original_index': original_index_from_manifest, 'filename': original_filename, 'title_for_display': display_title, 'decision': 'PROMPT_ERROR', 'reasoning': 'Failed to construct LLM prompt.'}
        
        api_result = call_llm_api(prompt_data, llm_provider_name, llm_model_id, llm_api_key, llm_base_url)
        
        # 添加错误处理和恢复机制
        if api_result and isinstance(api_result, dict):
            decision = api_result.get('label', 'API_ERROR')
            reasoning = api_result.get('justification', 'API call failed or returned invalid data.')
            
            # 检查是否需要恢复
            if decision in ['API_TIMEOUT', 'API_HTTP_ERROR_N/A', 'SCRIPT_ERROR']:
                app_logger.warning(f"Batch PDF screening error detected for {original_filename}: {decision} - {reasoning}")
                
                # 尝试恢复
                from app.utils.utils import handle_processing_error_recovery
                error_result = {'decision': 'PROCESSING_ERROR', 'reasoning': f'Batch PDF screening failed: {reasoning}'}
                item_data = {
                    'abstract': full_text[:2000],  # 使用前2000字符作为摘要
                    'title': display_title
                }
                
                recovery_result = handle_processing_error_recovery(
                    error_result, item_data, llm_provider_name, llm_model_id, llm_api_key, llm_base_url, criteria_prompt_text
                )
                
                if recovery_result.get('decision') in ['INCLUDE', 'EXCLUDE', 'MAYBE']:
                    app_logger.info(f"Batch PDF screening recovered successfully for {original_filename}: {recovery_result.get('decision')}")
                    decision = recovery_result.get('decision')
                    reasoning = f"[RECOVERED] {recovery_result.get('reasoning')}"
                else:
                    app_logger.warning(f"Batch PDF screening recovery failed for {original_filename}: {recovery_result.get('reasoning')}")
                    decision = recovery_result.get('decision', 'RECOVERY_FAILED')
                    reasoning = recovery_result.get('reasoning', 'Recovery attempt failed')
        else:
            decision = 'API_ERROR'
            reasoning = 'API call returned invalid response format'
        
        result_to_return = {
            'original_index': original_index_from_manifest, # Add original_index to the successful result
            'filename': original_filename, 
            'title_for_display': display_title, 
            'decision': decision,
            'reasoning': reasoning
        }
        app_logger.info(f"Batch PDF Thread: Returning result for '{original_filename}': {result_to_return}") # Log the entire result
        return result_to_return

    except Exception as e_process:
        app_logger.exception(f"Batch PDF Thread: Error processing file '{original_filename}': {e_process}")
        error_result = {'original_index': original_index_from_manifest, 'filename': original_filename, 'title_for_display': display_title, 'decision': 'FILE_PROCESSING_ERROR', 'reasoning': str(e_process)}
        app_logger.info(f"Batch PDF Thread: Returning error result for '{original_filename}': {error_result}")
        return error_result
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
    
    results = batch_data.get('results', [])
    # --- NEW: Calculate decision statistics --- 
    decision_counts = {
        'INCLUDE': 0, 'EXCLUDE': 0, 'MAYBE': 0,
        'TEXT_EXTRACT_ERROR': 0, 'PROMPT_ERROR': 0, 'API_ERROR': 0, 
        'FILE_PROCESSING_ERROR': 0, 'WORKER_THREAD_ERROR': 0, 'ERROR': 0 # Generic ERROR and other specific ones
    }
    for result_item in results:
        decision = result_item.get('decision', 'ERROR').upper()
        if decision in decision_counts:
            decision_counts[decision] += 1
        else: # Catch any other unforeseen decision strings as generic ERROR
            decision_counts['ERROR'] +=1
    # --- END NEW --- 

    app_logger.info(f"Rendering batch PDF results for {batch_session_id}. Contains {len(results)} items.")

    return render_template('batch_pdf_results.html', 
                           batch_info=batch_data, 
                           batch_id=batch_session_id,
                           results=results,  # Add results variable for template
                           decision_counts=decision_counts, # Pass counts to template
                           current_year=datetime.datetime.now().year)


# --- NEW: Download Route for Batch PDF Screening Results ---
@app.route('/download_batch_pdf_results/<batch_session_id>/<format>', methods=['GET'], endpoint='download_batch_pdf_results_placeholder')
def download_batch_pdf_results(batch_session_id, format):
    app_logger.info(f"Request to download batch PDF results for ID: {batch_session_id}, Format: {format}")
    batch_data = full_screening_sessions.get(batch_session_id)

    if not batch_data or not batch_data.get('is_batch_pdf_result', False):
        app_logger.warning(f"Download Batch PDF: Results not found or invalid for ID: {batch_session_id}")
        flash("Batch PDF screening results for download not found or may have expired.", "warning")
        # Redirect to the page where they might have come from or a sensible default
        return redirect(request.referrer or url_for('full_text_screening_page'))
        
    results_list = batch_data.get('results', [])
    # Use a generic base name or derive from batch info if available
    batch_name_info = batch_data.get('filename', 'batch_pdf_screening')
    filename_base = secure_filename(batch_name_info).replace('Batch_PDF_Results_', '').replace('_', ' ').replace('processed', '').strip().replace(' ', '_')
    if not filename_base: filename_base = "batch_pdf_results"

    if not results_list:
         app_logger.warning(f"Download Batch PDF: No actual result items found in batch data for ID: {batch_session_id}")
         flash("No result items found within the batch data to download.", "warning")
         return redirect(request.referrer or url_for('full_text_screening_page'))
    
    try:
        # The results_list should be a list of dicts, suitable for DataFrame
        # Ensure we are selecting relevant columns for download, including 'title_for_display'
        df_export_data = []
        for item in results_list:
            df_export_data.append({
                'Filename (Original)': item.get('filename'),
                'Display Title': item.get('title_for_display'),
                'Decision': item.get('decision'),
                'Reasoning': item.get('reasoning')
            })
        df = pd.DataFrame(df_export_data)

    except Exception as e:
         app_logger.exception(f"Download Batch PDF: Error converting results to DataFrame for batch ID {batch_session_id}")
         flash(f"Error preparing data for download: {e}", "error")
         return redirect(request.referrer or url_for('full_text_screening_page'))

    output_buffer = None
    mimetype = None
    download_filename = None

    try:
        if format == 'csv':
            output_buffer = io.StringIO()
            df.to_csv(output_buffer, index=False, encoding='utf-8-sig')
            mimetype = 'text/csv'
            download_filename = f"{filename_base}_batch_results.csv"
            bytes_buffer = io.BytesIO(output_buffer.getvalue().encode('utf-8-sig'))
            output_buffer = bytes_buffer 
            output_buffer.seek(0)
        elif format == 'xlsx':
            output_buffer = io.BytesIO()
            with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Batch PDF Results')
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            download_filename = f"{filename_base}_batch_results.xlsx"
            output_buffer.seek(0)
        elif format == 'json':
            output_buffer = io.StringIO()
            # df.to_json will convert the DataFrame to JSON, if direct list of dicts is preferred, use json.dumps(results_list)
            json_data_to_dump = df.to_dict(orient='records') # Convert df to list of dicts for consistent JSON structure
            json.dump(json_data_to_dump, output_buffer, indent=4)
            mimetype = 'application/json'
            download_filename = f"{filename_base}_batch_results.json"
            bytes_buffer = io.BytesIO(output_buffer.getvalue().encode('utf-8'))
            output_buffer = bytes_buffer
            output_buffer.seek(0)
        else:
            flash(f"Unsupported download format: {format}", "error")
            return redirect(request.referrer or url_for('full_text_screening_page'))

        return send_file(
            output_buffer,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_filename
        )

    except Exception as e:
        app_logger.exception(f"Download Batch PDF: Error generating download file for batch ID {batch_session_id}, format {format}")
        flash(f"Error generating download file ({format}): {e}", "error")
        return redirect(request.referrer or url_for('full_text_screening_page'))
# --- END NEW Batch PDF Download Route ---

# --- NEW: Export PDF Results by Decision Type ---
@app.route('/export_pdf_results/<decision>', methods=['GET'], endpoint='export_pdf_results')
def export_pdf_results(decision):
    """Export PDF screening results filtered by decision type"""
    try:
        # Get the current batch session ID from request args or session
        batch_session_id = request.args.get('batch_id')
        if not batch_session_id:
            flash("No batch session ID provided for export.", "error")
            return redirect(url_for('full_text_screening_page'))
        
        batch_data = full_screening_sessions.get(batch_session_id)
        if not batch_data or not batch_data.get('is_batch_pdf_result', False):
            flash("Batch PDF results not found for export.", "error")
            return redirect(url_for('show_batch_pdf_results', batch_session_id=batch_session_id) if batch_session_id else url_for('full_text_screening_page'))
        
        results_list = batch_data.get('results', [])
        if not results_list:
            flash("No results found for export.", "warning")
            return redirect(url_for('show_batch_pdf_results', batch_session_id=batch_session_id))
        
        # Filter results by decision type
        valid_decisions = ['INCLUDE', 'EXCLUDE', 'MAYBE', 'ERROR', 'ALL']
        if decision.upper() not in valid_decisions:
            flash(f"Invalid decision filter: {decision}", "error")
            return redirect(url_for('show_batch_pdf_results', batch_session_id=batch_session_id))
        
        if decision.upper() == 'ALL':
            filtered_results = results_list
            filter_description = "all results"
        else:
            filtered_results = [r for r in results_list if r.get('decision', '').upper() == decision.upper()]
            filter_description = f"results with decision '{decision.upper()}'"
        
        if not filtered_results:
            flash(f"No results found for decision type '{decision.upper()}'.", "warning")
            return redirect(url_for('show_batch_pdf_results', batch_session_id=batch_session_id))
        
        # Prepare export data
        batch_name_info = batch_data.get('filename', 'batch_pdf_screening')
        filename_base = secure_filename(batch_name_info).replace('Batch_PDF_Results_', '').replace('_', ' ').replace('processed', '').strip().replace(' ', '_')
        if not filename_base:
            filename_base = "batch_pdf_results"
        
        # Create DataFrame for export
        df_export_data = []
        for item in filtered_results:
            df_export_data.append({
                'Filename (Original)': item.get('filename'),
                'Display Title': item.get('title_for_display'),
                'Decision': item.get('decision'),
                'Reasoning': item.get('reasoning')
            })
        
        df = pd.DataFrame(df_export_data)
        
        # Default to CSV export
        output_buffer = io.StringIO()
        df.to_csv(output_buffer, index=False, encoding='utf-8-sig')
        download_filename = f"{filename_base}_{decision.lower()}_results.csv"
        
        bytes_buffer = io.BytesIO(output_buffer.getvalue().encode('utf-8-sig'))
        bytes_buffer.seek(0)
        
        return send_file(
            bytes_buffer,
            mimetype='text/csv',
            as_attachment=True,
            download_name=download_filename
        )
        
    except Exception as e:
        app_logger.exception(f"Error exporting PDF results for decision {decision}")
        flash(f"Error exporting results: {str(e)}", "error")
        batch_session_id = request.args.get('batch_id')
        return redirect(url_for('show_batch_pdf_results', batch_session_id=batch_session_id) if batch_session_id else url_for('full_text_screening_page'))

# --- Scheduled Cleanup Task for Expired PDFs ---
def cleanup_expired_pdf_files():
    app_logger.info("Scheduler: Running cleanup job for single-preview PDF files...")
    upload_dir = app.config.get('UPLOAD_FOLDER', 'uploads') # Get upload folder from app config
    if not os.path.isdir(upload_dir):
        app_logger.error(f"Scheduler: Upload directory '{upload_dir}' not found. Cleanup job aborted.")
        return

    count_deleted = 0
    count_checked = 0
    current_time = time.time()
    # Define a grace period for files, e.g., older than cache TTL + some buffer, or a fixed duration like 7 days
    # For TTLCache based on access, checking against the cache is more direct.
    # Files are named <uuid>_<original_filename>.pdf

    for filename in os.listdir(upload_dir):
        # Identify files potentially saved by screen_pdf_decision (single PDF preview)
        # These have a UUIDHoffentlich at the start of their name, then an underscore, then the original filename.
        # Batch processing files are named `batch_processing_<uuid>_<original_filename>.pdf` and are cleaned by their threads.
        if not filename.startswith("batch_processing_") and "_" in filename and filename.lower().endswith(".pdf"):
            count_checked += 1
            try:
                # Extract the UUID part (pdf_screening_id) from the filename
                # Example: a84dace3-4f7b-4ce2-8da2-571fbddce432_my_document.pdf
                # We need to be careful if original_filename itself contains underscores.
                # A safer way would be to ensure saved_pdf_filename in screen_pdf_decision strictly uses ONLY UUID + .pdf, 
                # and original filename is only stored in metadata.
                # For now, let's assume the first part before the first underscore after 36 chars (UUID length) is the ID.
                # This is a bit fragile. A better naming convention would be <UUID>.pdf for these files.
                
                # Attempt to extract UUID: UUIDs are 36 characters long (32 hex + 4 hyphens)
                potential_uuid = filename[:36]
                is_valid_uuid = False
                try:
                    uuid.UUID(potential_uuid, version=4)
                    is_valid_uuid = True
                except ValueError:
                    is_valid_uuid = False
                
                if is_valid_uuid and filename[36] == '_':
                    pdf_id_from_filename = potential_uuid
                    
                    # Check if this ID is still in our TTLCache
                    # The TTLCache automatically handles expiration.
                    # If pdf_id_from_filename is NOT in pdf_screening_results, it means the entry has expired.
                    if pdf_id_from_filename not in pdf_screening_results:
                        file_path_to_delete = os.path.join(upload_dir, filename)
                        try:
                            os.remove(file_path_to_delete)
                            count_deleted += 1
                            app_logger.info(f"Scheduler: Deleted expired PDF: {file_path_to_delete} (ID: {pdf_id_from_filename} not in active cache)")
                        except OSError as e_remove:
                            app_logger.error(f"Scheduler: Error deleting file {file_path_to_delete}: {e_remove}")
                    else:
                        app_logger.debug(f"Scheduler: PDF {filename} (ID: {pdf_id_from_filename}) still active in cache, not deleting.")
                else:
                    app_logger.debug(f"Scheduler: Filename '{filename}' does not match expected single-preview PDF pattern for cleanup.")

            except Exception as e_file_loop:
                app_logger.error(f"Scheduler: Error processing file '{filename}' for cleanup: {e_file_loop}")
    
    app_logger.info(f"Scheduler: Cleanup job finished. Checked {count_checked} potential single-preview files, deleted {count_deleted} expired files.")

# --- Initialize and start APScheduler ---
# We only want the scheduler to run in the main Gunicorn process, not in reloader or multiple workers if not careful.
# Gunicorn typically runs multiple worker processes. The scheduler should ideally run in only one process
# or be managed by a central service if you have multiple app instances.
# For a simple setup with Gunicorn, running it in the main process before workers are forked, or
# ensuring only one worker runs it, can be tricky. A common approach for Gunicorn is to run the scheduler
# in a separate process or use a Gunicorn-specific mechanism if available.

# Simplest approach for now (might run per Gunicorn worker if not managed carefully, or use a lock file):
# For Render.com or similar PaaS with single instance type, this might be okay.
# If running multiple Gunicorn workers, this job will be scheduled by each worker independently.
# This isn't ideal for a cleanup task that acts on a shared resource like the filesystem.
# A better solution for multi-worker Gunicorn involves a lock or a dedicated scheduler process.

# Let's assume for now a simpler scenario or that Gunicorn is run with 1 worker for this scheduler.
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true': # Avoid running in Flask reloader sub-process
    scheduler = BackgroundScheduler(daemon=True)
    # Run cleanup job daily at, for example, 2:30 AM server time
    scheduler.add_job(cleanup_expired_pdf_files, 'cron', hour=2, minute=30)
    try:
        scheduler.start()
        app_logger.info("APScheduler started for PDF cleanup.")
        # Shut down the scheduler when exiting the app
        atexit.register(lambda: scheduler.shutdown())
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        app_logger.info("APScheduler shutdown due to interrupt.")
    except Exception as e_scheduler_start:
        app_logger.error(f"Error starting APScheduler: {e_scheduler_start}")

# --- Run App ---
if __name__ == '__main__':
    app_logger.info("Starting Flask app in debug mode...") # Example for __main__
    app.run(debug=True, host='0.0.0.0', port=5050)#test

# --- Celery Async Task Routes ---
@app.route('/async_literature_screening', methods=['POST'])
def async_literature_screening():
    """Start asynchronous literature screening using Celery"""
    if not CELERY_ENABLED:
        return jsonify({
            'status': 'error',
            'message': 'Async processing not available. Celery is not configured.'
        }), 503
    
    try:
        # Validate file upload
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400
        
        uploaded_file = request.files['file']
        if uploaded_file.filename == '' or not allowed_file(uploaded_file.filename):
            return jsonify({'status': 'error', 'message': 'Invalid file type'}), 400
        
        # Save uploaded file temporarily
        temp_file_path = os.path.join(UPLOAD_FOLDER, f"async_lit_{uuid.uuid4()}.ris")
        uploaded_file.save(temp_file_path)
        
        # Get form data
        line_range_input = request.form.get('line_range_filter', '').strip()
        title_filter_input = request.form.get('title_text_filter', '').strip()
        
        # Parse line range if provided
        line_range = None
        if line_range_input:
            try:
                # Quick check of file size to get total count
                with open(temp_file_path, 'rb') as f:
                    df_temp = load_literature_ris(f)
                    total_count = len(df_temp) if df_temp is not None else 0
                start_idx, end_idx = parse_line_range(line_range_input, total_count)
                line_range = (start_idx, end_idx)
            except Exception as e:
                os.remove(temp_file_path)
                return jsonify({'status': 'error', 'message': f'Invalid line range: {str(e)}'}), 400
        
        # Get screening criteria and LLM config
        criteria_prompt = get_screening_criteria()
        llm_config = get_current_llm_config(session)
        llm_config['system_prompt'] = DEFAULT_SYSTEM_PROMPT
        
        # Generate screening ID
        screening_id = str(uuid.uuid4())
        
        # Start Celery task
        task = process_literature_screening.delay(
            temp_file_path,
            criteria_prompt,
            llm_config,
            dict(session),  # Convert session to dict for serialization
            screening_id,
            line_range,
            title_filter_input
        )
        
        app_logger.info(f"Started async literature screening task {task.id} for screening {screening_id}")
        
        return jsonify({
            'status': 'success',
            'task_id': task.id,
            'screening_id': screening_id,
            'message': 'Literature screening started. Check progress using task_id.'
        })
        
    except Exception as e:
        app_logger.exception(f"Error starting async literature screening: {e}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

@app.route('/async_pdf_screening', methods=['POST'])
def async_pdf_screening():
    """Start asynchronous PDF screening using Celery"""
    if not CELERY_ENABLED:
        return jsonify({
            'status': 'error', 
            'message': 'Async processing not available. Celery is not configured.'
        }), 503
    
    try:
        # Validate file uploads
        if 'pdfs' not in request.files:
            return jsonify({'status': 'error', 'message': 'No PDF files uploaded'}), 400
        
        uploaded_files = request.files.getlist('pdfs')
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            return jsonify({'status': 'error', 'message': 'No valid PDF files selected'}), 400
        
        # Save uploaded PDFs temporarily
        pdf_files_info = []
        for uploaded_file in uploaded_files:
            if uploaded_file.filename != '' and uploaded_file.filename.lower().endswith('.pdf'):
                temp_file_path = os.path.join(UPLOAD_FOLDER, f"async_pdf_{uuid.uuid4()}_{uploaded_file.filename}")
                uploaded_file.save(temp_file_path)
                pdf_files_info.append({
                    'path': temp_file_path,
                    'filename': uploaded_file.filename
                })
        
        if not pdf_files_info:
            return jsonify({'status': 'error', 'message': 'No valid PDF files were processed'}), 400
        
        # Get screening criteria and LLM config
        criteria_prompt = get_screening_criteria()
        llm_config = get_current_llm_config(session)
        llm_config['system_prompt'] = DEFAULT_SYSTEM_PROMPT
        
        # Generate batch ID
        batch_id = str(uuid.uuid4())
        
        # Start Celery task
        task = process_pdf_screening.delay(
            pdf_files_info,
            criteria_prompt,
            llm_config,
            dict(session),  # Convert session to dict for serialization
            batch_id
        )
        
        app_logger.info(f"Started async PDF screening task {task.id} for batch {batch_id} with {len(pdf_files_info)} files")
        
        return jsonify({
            'status': 'success',
            'task_id': task.id,
            'batch_id': batch_id,
            'total_files': len(pdf_files_info),
            'message': 'PDF screening started. Check progress using task_id.'
        })
        
    except Exception as e:
        app_logger.exception(f"Error starting async PDF screening: {e}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

@app.route('/async_quality_assessment', methods=['POST'])
def async_quality_assessment():
    """Start asynchronous quality assessment using Celery"""
    if not CELERY_ENABLED:
        return jsonify({
            'status': 'error',
            'message': 'Async processing not available. Celery is not configured.'
        }), 503
    
    try:
        # Validate file uploads
        if 'pdf_files' not in request.files:
            return jsonify({'status': 'error', 'message': 'No PDF files uploaded'}), 400
        
        uploaded_files = request.files.getlist('pdf_files')
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            return jsonify({'status': 'error', 'message': 'No valid PDF files selected'}), 400
        
        # Save uploaded PDFs temporarily
        files_info = []
        for uploaded_file in uploaded_files:
            if uploaded_file.filename != '' and uploaded_file.filename.lower().endswith('.pdf'):
                temp_file_path = os.path.join(UPLOAD_FOLDER, f"async_qa_{uuid.uuid4()}_{uploaded_file.filename}")
                uploaded_file.save(temp_file_path)
                files_info.append({
                    'path': temp_file_path,
                    'filename': uploaded_file.filename
                })
        
        if not files_info:
            return jsonify({'status': 'error', 'message': 'No valid PDF files were processed'}), 400
        
        # Get assessment configuration
        selected_document_type = request.form.get('document_type')
        assessment_config = {
            'document_type': selected_document_type,
            'quality_tools': QUALITY_ASSESSMENT_TOOLS
        }
        
        # Get LLM config
        llm_config = get_current_llm_config(session)
        llm_config['system_prompt'] = DEFAULT_SYSTEM_PROMPT
        
        # Generate assessment ID
        assessment_id = str(uuid.uuid4())
        
        # Start Celery task
        task = process_quality_assessment.delay(
            files_info,
            assessment_config,
            llm_config,
            dict(session),  # Convert session to dict for serialization
            assessment_id
        )
        
        app_logger.info(f"Started async quality assessment task {task.id} for assessment {assessment_id} with {len(files_info)} files")
        
        return jsonify({
            'status': 'success',
            'task_id': task.id,
            'assessment_id': assessment_id,
            'total_files': len(files_info),
            'message': 'Quality assessment started. Check progress using task_id.'
        })
        
    except Exception as e:
        app_logger.exception(f"Error starting async quality assessment: {e}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

@app.route('/task_progress/<task_id>')
def task_progress(task_id):
    """Get progress of a Celery task"""
    if not CELERY_ENABLED:
        return jsonify({
            'status': 'error',
            'message': 'Task monitoring not available. Celery is not configured.'
        }), 503
    
    try:
        progress = get_task_progress(task_id)
        return jsonify({
            'status': 'success',
            'progress': progress
        })
    except Exception as e:
        app_logger.exception(f"Error getting task progress for {task_id}: {e}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

@app.route('/task_result/<task_id>')
def task_result(task_id):
    """Get result of a completed Celery task"""
    if not CELERY_ENABLED:
        return jsonify({
            'status': 'error',
            'message': 'Task results not available. Celery is not configured.'
        }), 503
    
    try:
        result = get_task_result(task_id)
        return jsonify({
            'status': 'success',
            'result': result
        })
    except Exception as e:
        app_logger.exception(f"Error getting task result for {task_id}: {e}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

@app.route('/cancel_task/<task_id>', methods=['POST'])
def cancel_task(task_id):
    """Cancel a running Celery task"""
    if not CELERY_ENABLED:
        return jsonify({
            'status': 'error',
            'message': 'Task cancellation not available. Celery is not configured.'
        }), 503
    
    try:
        celery.control.revoke(task_id, terminate=True)
        app_logger.info(f"Cancelled task {task_id}")
        return jsonify({
            'status': 'success',
            'message': f'Task {task_id} cancelled successfully'
        })
    except Exception as e:
        app_logger.exception(f"Error cancelling task {task_id}: {e}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

@app.route('/async_results/<result_type>/<result_id>')
def async_results(result_type, result_id):
    """Get results from async processing tasks"""
    try:
        if result_type == 'screening':
            # Get literature screening results
            results_data = redis_client.get(f"screening_results:{result_id}")
            if results_data:
                data = pickle.loads(results_data)
                return render_template('screening_results.html', 
                                     screening_data=data, 
                                     screening_id=result_id,
                                     current_year=datetime.datetime.now().year)
        
        elif result_type == 'pdf_batch':
            # Get PDF batch screening results
            results_data = redis_client.get(f"pdf_batch_results:{result_id}")
            if results_data:
                data = pickle.loads(results_data)
                return render_template('pdf_batch_results.html',
                                     batch_data=data,
                                     batch_id=result_id,
                                     current_year=datetime.datetime.now().year)
        
        elif result_type == 'quality':
            # Get quality assessment results
            results_data = redis_client.get(f"quality_results:{result_id}")
            if results_data:
                data = pickle.loads(results_data)
                return render_template('quality_results.html',
                                     assessment_data=data,
                                     assessment_id=result_id,
                                     current_year=datetime.datetime.now().year)
        
        flash('Results not found or may have expired.', 'warning')
        return redirect(url_for('screening_actions_page'))
        
    except Exception as e:
        app_logger.exception(f"Error retrieving async results {result_type}/{result_id}: {e}")
        flash(f'Error retrieving results: {str(e)}', 'error')
        return redirect(url_for('screening_actions_page'))

# --- End Celery Routes ---

# --- Full Dataset Screening State Management ---
@app.route('/save_screening_state', methods=['POST'])
def save_screening_state():
    """Save screening state to server for later resuming"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        # Generate a unique resume ID
        resume_id = str(uuid.uuid4())
        
        # Extract necessary information
        resume_point = data.get('resume_point', 0)
        processed_items = data.get('processed_items', [])
        
        # Save filter information
        filter_info = {
            'title_filter': data.get('title_filter', ''),
            'line_range': data.get('line_range', '')
        }
        
        # Save state to Redis or session storage
        state_data = {
            'resume_point': resume_point,
            'processed_items': processed_items,
            'filter_info': filter_info,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        store_full_screening_session(f"state_{resume_id}", state_data)
        app_logger.info(f"Saved screening state with resume ID: {resume_id}, resume point: {resume_point}, items: {len(processed_items)}")
        
        return jsonify({
            "status": "success", 
            "resume_id": resume_id
        })
    except Exception as e:
        app_logger.exception(f"Error saving screening state: {e}")
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

# Network health check endpoint
@app.route('/health/network')
def network_health_check():
    """网络健康检查端点"""
    import requests
    results = {}
    
    endpoints = {
        "DeepSeek": "https://api.deepseek.com",
        "OpenAI": "https://api.openai.com", 
        "Claude": "https://api.anthropic.com",
        "Gemini": "https://generativelanguage.googleapis.com"
    }
    
    for name, url in endpoints.items():
        try:
            response = requests.get(url, timeout=10)
            results[name] = {"status": "ok", "code": response.status_code}
        except Exception as e:
            results[name] = {"status": "error", "error": str(e)}
    
    return jsonify(results)

# Legacy URL redirect for quality assessment
@app.route('/quality/')
@app.route('/quality/<path:path>')
def redirect_old_quality_urls(path=None):
    """Redirect old /quality/ URLs to new /quality_assessment/ URLs"""
    if path:
        return redirect(f'/quality_assessment/{path}', code=301)
    else:
        return redirect('/quality_assessment/', code=301)


