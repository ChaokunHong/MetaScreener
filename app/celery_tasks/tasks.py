import os
import sys
import time
import logging
import traceback
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from celery import Task
from celery.exceptions import Retry
import redis
import pickle

# Add the parent directory to the path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.celery_tasks.celery_app import celery
from app.utils.utils import load_literature_ris, extract_text_from_pdf, call_llm_api, _parse_llm_response
from config.config import get_llm_providers_info, get_api_key_for_provider, get_base_url_for_provider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis client for storing results and progress
redis_client = redis.Redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))

def _prepare_quality_assessment_prompt(text, config):
    """Prepare the quality assessment prompt"""
    # This would be customized based on your quality assessment criteria
    base_prompt = """
    Please assess the quality of this research document based on the following criteria:
    1. Methodology clarity and rigor
    2. Data presentation and analysis
    3. Literature review completeness
    4. Conclusion validity
    5. Overall scientific quality
    
    Document content:
    {text}
    
    Please provide:
    - A quality score from 1-10
    - Detailed assessment of each criterion
    - Specific recommendations for improvement
    
    Format your response as JSON with keys: score, details, recommendations
    """
    return base_prompt.format(text=text[:5000])  # Limit text length

def _parse_quality_response(response):
    """Parse the quality assessment response"""
    try:
        # Try to parse as JSON first
        import json
        return json.loads(response)
    except:
        # Fallback to text parsing
        return {
            'score': 5,  # Default score
            'details': response,
            'recommendations': ['Manual review recommended']
        }

class CallbackTask(Task):
    """Base task class with error handling and callbacks"""
    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Task {task_id} completed successfully")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}")
        # Store error in Redis for frontend retrieval
        redis_client.setex(f"task_error:{task_id}", 3600, str(exc))

@celery.task(bind=True, base=CallbackTask, queue='literature_screening')
def process_literature_screening(self, file_path, criteria_prompt, llm_config, session_data, screening_id, line_range=None, title_filter=None):
    """
    Process literature screening for RIS files
    
    Args:
        file_path: Path to the uploaded RIS file
        criteria_prompt: Screening criteria text
        llm_config: LLM configuration dict
        session_data: User session data
        screening_id: Unique screening session ID
        line_range: Optional range of lines to process (tuple)
        title_filter: Optional title filter string
    """
    try:
        # Update task progress
        self.update_state(state='PROGRESS', meta={'current': 0, 'total': 0, 'status': 'Loading literature data...'})
        
        # Load literature data
        literature_data = load_literature_ris(file_path)
        if literature_data.empty:
            raise ValueError("No valid literature data found in file")
        
        total_items = len(literature_data)
        
        # Apply filters if specified
        if line_range:
            start_idx, end_idx = line_range
            literature_data = literature_data.iloc[start_idx:end_idx]
        
        if title_filter:
            mask = literature_data['title'].str.contains(title_filter, case=False, na=False)
            literature_data = literature_data[mask]
        
        filtered_total = len(literature_data)
        
        # Update progress
        self.update_state(state='PROGRESS', meta={
            'current': 0, 
            'total': filtered_total, 
            'status': f'Processing {filtered_total} items...'
        })
        
        # Get LLM configuration
        provider_name = llm_config['provider_name']
        model_id = llm_config['model_id']
        api_key = get_api_key_for_provider(provider_name, session_data)
        base_url = get_base_url_for_provider(provider_name)
        
        if not api_key:
            raise ValueError(f"No API key found for provider {provider_name}")
        
        # Process literature items
        results = []
        for index, (_, row) in enumerate(literature_data.iterrows()):
            try:
                # Extract abstract and title
                abstract = row.get('abstract', '')
                title = row.get('title', '')
                
                if not abstract and not title:
                    result = {
                        'title': title,
                        'abstract': abstract,
                        'ai_decision': 'EXCLUDE',
                        'ai_justification': 'No abstract or title available for screening',
                        'processing_time': 0.0,
                        'error': None
                    }
                else:
                    # Prepare prompt
                    prompt_dict = {
                        'system_prompt': llm_config.get('system_prompt', ''),
                        'main_prompt': criteria_prompt.format(abstract=abstract)
                    }
                    
                    # Process with LLM
                    start_time = time.time()
                    ai_response = call_llm_api(
                        prompt_dict, provider_name, model_id, api_key, base_url
                    )
                    processing_time = time.time() - start_time
                    
                    # Parse response
                    decision, justification = _parse_llm_response(ai_response)
                    
                    result = {
                        'title': title,
                        'abstract': abstract,
                        'ai_decision': decision,
                        'ai_justification': justification,
                        'processing_time': processing_time,
                        'error': None
                    }
                
                results.append(result)
                
                # Update progress
                current = index + 1
                self.update_state(state='PROGRESS', meta={
                    'current': current,
                    'total': filtered_total,
                    'status': f'Processed {current}/{filtered_total} items'
                })
                
                # Small delay to prevent API rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error processing item {index}: {e}")
                result = {
                    'title': row.get('title', ''),
                    'abstract': row.get('abstract', ''),
                    'ai_decision': 'ERROR',
                    'ai_justification': f'Processing error: {str(e)}',
                    'processing_time': 0.0,
                    'error': str(e)
                }
                results.append(result)
        
        # Store results in Redis
        results_data = {
            'results': results,
            'total_processed': len(results),
            'criteria_used': criteria_prompt,
            'llm_config': llm_config,
            'completed_at': time.time()
        }
        
        redis_client.setex(f"screening_results:{screening_id}", 86400, pickle.dumps(results_data))
        
        # Clean up temp file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"Could not remove temp file {file_path}: {e}")
        
        return {
            'screening_id': screening_id,
            'total_processed': len(results),
            'status': 'completed'
        }
        
    except Exception as e:
        logger.error(f"Literature screening task failed: {e}")
        logger.error(traceback.format_exc())
        raise

@celery.task(bind=True, base=CallbackTask, queue='pdf_screening')
def process_pdf_screening(self, pdf_files, criteria_prompt, llm_config, session_data, batch_id):
    """
    Process PDF screening for multiple PDF files
    
    Args:
        pdf_files: List of PDF file paths
        criteria_prompt: Screening criteria text
        llm_config: LLM configuration dict
        session_data: User session data
        batch_id: Unique batch processing ID
    """
    try:
        total_files = len(pdf_files)
        self.update_state(state='PROGRESS', meta={
            'current': 0, 
            'total': total_files, 
            'status': 'Starting PDF processing...'
        })
        
        # Get LLM configuration
        provider_name = llm_config['provider_name']
        model_id = llm_config['model_id']
        api_key = get_api_key_for_provider(provider_name, session_data)
        base_url = get_base_url_for_provider(provider_name)
        
        if not api_key:
            raise ValueError(f"No API key found for provider {provider_name}")
        
        results = []
        for index, pdf_file_info in enumerate(pdf_files):
            try:
                file_path = pdf_file_info['path']
                original_filename = pdf_file_info['filename']
                
                # Extract text from PDF
                self.update_state(state='PROGRESS', meta={
                    'current': index + 1,
                    'total': total_files,
                    'status': f'Extracting text from {original_filename}...'
                })
                
                extracted_text = extract_text_from_pdf(file_path)
                
                if not extracted_text or len(extracted_text.strip()) < 50:
                    result = {
                        'filename': original_filename,
                        'extracted_text': extracted_text,
                        'ai_decision': 'EXCLUDE',
                        'ai_justification': 'Insufficient text extracted from PDF for screening',
                        'processing_time': 0.0,
                        'error': None
                    }
                else:
                    # Process with LLM
                    self.update_state(state='PROGRESS', meta={
                        'current': index + 1,
                        'total': total_files,
                        'status': f'Screening {original_filename} with AI...'
                    })
                    
                    prompt_dict = {
                        'system_prompt': llm_config.get('system_prompt', ''),
                        'main_prompt': criteria_prompt.format(abstract=extracted_text[:4000])  # Limit text length
                    }
                    
                    start_time = time.time()
                    ai_response = call_llm_api(
                        prompt_dict, provider_name, model_id, api_key, base_url
                    )
                    processing_time = time.time() - start_time
                    
                    # Parse response
                    decision, justification = _parse_llm_response(ai_response)
                    
                    result = {
                        'filename': original_filename,
                        'extracted_text': extracted_text,
                        'ai_decision': decision,
                        'ai_justification': justification,
                        'processing_time': processing_time,
                        'error': None
                    }
                
                results.append(result)
                
                # Clean up individual file
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    logger.warning(f"Could not remove PDF file {file_path}: {e}")
                
                # Small delay to prevent API rate limiting
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error processing PDF {pdf_file_info.get('filename', 'unknown')}: {e}")
                result = {
                    'filename': pdf_file_info.get('filename', 'unknown'),
                    'extracted_text': '',
                    'ai_decision': 'ERROR',
                    'ai_justification': f'Processing error: {str(e)}',
                    'processing_time': 0.0,
                    'error': str(e)
                }
                results.append(result)
        
        # Store results in Redis
        results_data = {
            'results': results,
            'total_processed': len(results),
            'criteria_used': criteria_prompt,
            'llm_config': llm_config,
            'completed_at': time.time()
        }
        
        redis_client.setex(f"pdf_batch_results:{batch_id}", 86400, pickle.dumps(results_data))
        
        return {
            'batch_id': batch_id,
            'total_processed': len(results),
            'status': 'completed'
        }
        
    except Exception as e:
        logger.error(f"PDF screening task failed: {e}")
        logger.error(traceback.format_exc())
        raise

@celery.task(bind=True, base=CallbackTask, queue='quality_assessment')
def process_quality_assessment(self, file_paths, assessment_config, llm_config, session_data, assessment_id):
    """
    Process quality assessment for uploaded documents
    
    Args:
        file_paths: List of document file paths
        assessment_config: Quality assessment configuration
        llm_config: LLM configuration dict
        session_data: User session data
        assessment_id: Unique assessment session ID
    """
    try:
        total_files = len(file_paths)
        self.update_state(state='PROGRESS', meta={
            'current': 0,
            'total': total_files,
            'status': 'Starting quality assessment...'
        })
        
        # Get LLM configuration
        provider_name = llm_config['provider_name']
        model_id = llm_config['model_id']
        api_key = get_api_key_for_provider(provider_name, session_data)
        base_url = get_base_url_for_provider(provider_name)
        
        if not api_key:
            raise ValueError(f"No API key found for provider {provider_name}")
        
        results = []
        for index, file_info in enumerate(file_paths):
            try:
                file_path = file_info['path']
                original_filename = file_info['filename']
                
                # Update progress
                self.update_state(state='PROGRESS', meta={
                    'current': index + 1,
                    'total': total_files,
                    'status': f'Assessing quality of {original_filename}...'
                })
                
                # Extract text based on file type
                if file_path.lower().endswith('.pdf'):
                    extracted_text = extract_text_from_pdf(file_path)
                else:
                    # Handle other file types as needed
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        extracted_text = f.read()
                
                if not extracted_text or len(extracted_text.strip()) < 100:
                    result = {
                        'filename': original_filename,
                        'quality_score': 0,
                        'assessment_details': 'Insufficient content for quality assessment',
                        'recommendations': ['File appears to be empty or corrupted'],
                        'processing_time': 0.0,
                        'error': None
                    }
                else:
                    # Prepare quality assessment prompt
                    assessment_prompt = _prepare_quality_assessment_prompt(
                        extracted_text, assessment_config
                    )
                    
                    prompt_dict = {
                        'system_prompt': llm_config.get('system_prompt', ''),
                        'main_prompt': assessment_prompt
                    }
                    
                    start_time = time.time()
                    ai_response = call_llm_api(
                        prompt_dict, provider_name, model_id, api_key, base_url
                    )
                    processing_time = time.time() - start_time
                    
                    # Parse quality assessment response
                    quality_data = _parse_quality_response(ai_response)
                    
                    result = {
                        'filename': original_filename,
                        'quality_score': quality_data.get('score', 0),
                        'assessment_details': quality_data.get('details', ''),
                        'recommendations': quality_data.get('recommendations', []),
                        'processing_time': processing_time,
                        'error': None
                    }
                
                results.append(result)
                
                # Clean up file
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    logger.warning(f"Could not remove file {file_path}: {e}")
                
                # Small delay to prevent API rate limiting
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error processing file {file_info.get('filename', 'unknown')}: {e}")
                result = {
                    'filename': file_info.get('filename', 'unknown'),
                    'quality_score': 0,
                    'assessment_details': f'Processing error: {str(e)}',
                    'recommendations': ['Manual review required due to processing error'],
                    'processing_time': 0.0,
                    'error': str(e)
                }
                results.append(result)
        
        # Store results in Redis
        results_data = {
            'results': results,
            'total_processed': len(results),
            'assessment_config': assessment_config,
            'llm_config': llm_config,
            'completed_at': time.time()
        }
        
        redis_client.setex(f"quality_results:{assessment_id}", 86400, pickle.dumps(results_data))
        
        return {
            'assessment_id': assessment_id,
            'total_processed': len(results),
            'status': 'completed'
        }
        
    except Exception as e:
        logger.error(f"Quality assessment task failed: {e}")
        logger.error(traceback.format_exc())
        raise

@celery.task(bind=True, base=CallbackTask, queue='maintenance')
def cleanup_temp_files(self, older_than_hours=24):
    """
    Clean up temporary files older than specified hours
    
    Args:
        older_than_hours: Remove files older than this many hours
    """
    try:
        import glob
        import time
        
        temp_dirs = ['uploads', 'temp', '/tmp/screen_webapp_*']
        current_time = time.time()
        cutoff_time = current_time - (older_than_hours * 3600)
        
        cleaned_count = 0
        
        for temp_pattern in temp_dirs:
            try:
                files = glob.glob(temp_pattern)
                for file_path in files:
                    try:
                        if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff_time:
                            os.remove(file_path)
                            cleaned_count += 1
                        elif os.path.isdir(file_path) and os.path.getmtime(file_path) < cutoff_time:
                            import shutil
                            shutil.rmtree(file_path)
                            cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"Could not remove {file_path}: {e}")
            except Exception as e:
                logger.warning(f"Error processing temp pattern {temp_pattern}: {e}")
        
        logger.info(f"Cleaned up {cleaned_count} temporary files/directories")
        return {'cleaned_count': cleaned_count, 'status': 'completed'}
        
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        raise

# Utility functions for task management
def get_task_result(task_id):
    """Get task result from Celery"""
    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=celery)
    return {
        'state': result.state,
        'info': result.info,
        'successful': result.successful(),
        'failed': result.failed()
    }

def get_task_progress(task_id):
    """Get task progress information"""
    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=celery)
    
    if result.state == 'PROGRESS':
        return result.info
    elif result.state == 'SUCCESS':
        return {'current': 100, 'total': 100, 'status': 'Completed'}
    elif result.state == 'FAILURE':
        return {'current': 0, 'total': 100, 'status': f'Failed: {str(result.info)}'}
    else:
        return {'current': 0, 'total': 100, 'status': result.state} 