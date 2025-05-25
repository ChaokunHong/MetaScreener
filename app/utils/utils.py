import rispy
import pandas as pd
from typing import List, Dict, Optional, IO, Union, Any
import requests
import json
import re
import traceback
import io
import fitz # PyMuPDF
import pytesseract # <--- Newly added import
from PIL import Image # <--- Newly added import
import logging # <-- Import logging
import time
import random

# For Gemini - Updated to use the new SDK
try:
    from google import genai
    GEMINI_SDK_VERSION = "new"
    print(f"Using new Google Gen AI SDK version: {GEMINI_SDK_VERSION}")
except ImportError:
    try:
        import google.generativeai as genai
        GEMINI_SDK_VERSION = "legacy"
        print(f"Using legacy Google Generative AI SDK version: {GEMINI_SDK_VERSION}")
    except ImportError:
        genai = None
        GEMINI_SDK_VERSION = "none"
        print("No Google Gemini SDK found")

# For Anthropic
from anthropic import Anthropic, APIStatusError, APIConnectionError, RateLimitError, APIError

# Import necessary items from config
from config.config import (
    SUPPORTED_LLM_PROVIDERS, # PICOT_TEMPLATE, # Ensure this is commented out or removed
    DEFAULT_SYSTEM_PROMPT, DEFAULT_OUTPUT_INSTRUCTIONS,
    get_screening_criteria, get_current_criteria_object,
    get_supported_criteria_frameworks, get_default_criteria_for_framework, get_current_framework_id,
    TESSERACT_CMD_PATH, PDF_OCR_THRESHOLD_CHARS,
    # Import optimization configurations
    SCREENING_OPTIMIZATION_CONFIG, BATCH_PROCESSING_CONFIG, QUALITY_ASSURANCE_CONFIG, MONITORING_CONFIG,
    get_screening_config, get_provider_specific_config, calculate_optimal_batch_size
)

# Get a logger for this module
utils_logger = logging.getLogger("metascreener_utils")

# Configure Tesseract path if specified in config
if TESSERACT_CMD_PATH:
    try:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD_PATH
        utils_logger.info(f"Tesseract OCR command path set to: {TESSERACT_CMD_PATH}")
    except Exception as e_tess_path:
        utils_logger.error(f"Error setting Tesseract OCR command path to '{TESSERACT_CMD_PATH}': {e_tess_path}")
else:
    utils_logger.info("Tesseract OCR command path not specified in config, using system PATH.")


# --- Data Loading Functions ---
def load_literature_ris(filepath_or_stream: Union[str, IO[bytes]]) -> Optional[pd.DataFrame]:
    entries = None
    source_description = ""
    try:
        if isinstance(filepath_or_stream, str):
            source_description = filepath_or_stream
            with open(filepath_or_stream, 'r', encoding='utf-8-sig') as bibliography_file:
                entries = list(rispy.load(bibliography_file))
        elif hasattr(filepath_or_stream, 'read'):
            source_description = "uploaded file stream"
            
            try:
                # Ensure stream is at the beginning if possible
                if hasattr(filepath_or_stream, 'seek') and callable(filepath_or_stream.seek):
                    filepath_or_stream.seek(0)
                
                # Read all bytes from the original stream
                binary_content = filepath_or_stream.read()
                
                # Create a new BytesIO stream from this content
                buffered_binary_stream = io.BytesIO(binary_content)
                
                # Now wrap this BytesIO stream with TextIOWrapper
                text_stream = io.TextIOWrapper(buffered_binary_stream, encoding='utf-8-sig', errors='replace')
                entries = list(rispy.load(text_stream))
            except Exception as e_stream_handling:
                utils_logger.exception(f"Error handling uploaded stream before RIS parsing: {source_description}")
                return None
        else:
            utils_logger.error(f"Invalid input type for load_literature_ris: {type(filepath_or_stream)}")
            return None

        if not entries:
            utils_logger.warning(f"RIS parsing resulted in no entries for {source_description}.")
            return pd.DataFrame()

        data_for_df = []
        for entry_num, entry in enumerate(entries):
            title = entry.get('title') or entry.get('primary_title') or \
                    entry.get('TI') or entry.get('T1')
            abstract = entry.get('abstract') or entry.get('AB') or entry.get('N2')
            authors_raw = entry.get('authors') or entry.get('AU') or entry.get('A1')
            authors = [a.strip() for a in authors_raw.split(';')] if isinstance(authors_raw, str) else (
                authors_raw if isinstance(authors_raw, list) else [])
            year = entry.get('year') or entry.get('PY') or entry.get('Y1')
            doi = entry.get('doi') or entry.get('DO') or entry.get('DI')
            data_for_df.append({
                'id': entry.get('id', f"entry_{entry_num + 1}"), 'title': title,
                'abstract': abstract, 'authors': authors, 'year': year, 'doi': doi,
            })
        df = pd.DataFrame(data_for_df)
        for col in ['title', 'abstract', 'authors']:  # Ensure essential columns
            if col not in df.columns:
                df[col] = None if col != 'authors' else [[] for _ in range(len(df))]
        return df
    except FileNotFoundError:
        utils_logger.error(f"Error: RIS file not found: {source_description}")
        return None
    except UnicodeDecodeError as e:
        utils_logger.error(f"Error decoding RIS file {source_description}: {e}")
        return None
    except Exception as e:
        utils_logger.exception(f"Error reading/parsing RIS file {source_description}")
        traceback.print_exc()
        return None


# --- PDF Text Extraction (Enhanced with Page/Line Numbers and OCR Fallback) --- 
def extract_text_from_pdf(file_stream: IO[bytes], ocr_language: str = 'eng') -> Optional[str]:
    """Extracts text content from a PDF file stream.
    Uses PyMuPDF for direct text extraction, falls back to Tesseract OCR for image-based pages,
    and prepends page and line number information to the extracted text.
    """
    text_pages_with_line_numbers = []
    pdf_data = None

    try:
        utils_logger.debug("Reading PDF file stream into bytes...")
        pdf_data = file_stream.read()
        if not pdf_data:
             utils_logger.error("PDF file stream was empty after read.")
             return None
        utils_logger.debug(f"Read {len(pdf_data)} bytes. Opening with PyMuPDF...")
        
        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            if doc.page_count == 0:
                utils_logger.error("PDF has 0 pages or could not be parsed correctly.")
                return None
            utils_logger.info(f"PDF has {doc.page_count} pages. Extracting text, adding page/line numbers, with OCR fallback...")

            for page_num_0_indexed, page in enumerate(doc):
                page_num_1_indexed = page_num_0_indexed + 1
                page_header = f"--- TEXT FROM PDF Page {page_num_1_indexed} ---"
                
                page_text_direct = page.get_text("text", sort=True).strip()
                current_page_raw_text = page_text_direct

                if len(page_text_direct) < PDF_OCR_THRESHOLD_CHARS:
                    utils_logger.info(f"Page {page_num_1_indexed}: Direct text short ({len(page_text_direct)} chars, threshold: {PDF_OCR_THRESHOLD_CHARS}). Attempting OCR.")
                    try:
                        pix = page.get_pixmap(dpi=300) 
                        img_bytes = pix.tobytes("png")
                        pil_image = Image.open(io.BytesIO(img_bytes))
                        ocr_text = pytesseract.image_to_string(pil_image, lang=ocr_language).strip()
                        
                        if ocr_text:
                            if (len(ocr_text) > len(page_text_direct) + PDF_OCR_THRESHOLD_CHARS) or \
                               (not page_text_direct and ocr_text):
                                current_page_raw_text = ocr_text
                                utils_logger.info(f"Page {page_num_1_indexed}: Used OCR text ({len(ocr_text)} chars).")
                            else:
                                utils_logger.info(f"Page {page_num_1_indexed}: OCR text not substantially better or direct was sufficient. Using direct text ({len(page_text_direct)} chars).")
                        else:
                            utils_logger.info(f"Page {page_num_1_indexed}: OCR did not yield text. Using direct text.")
                    except Exception as e_ocr:
                        utils_logger.warning(f"Page {page_num_1_indexed}: OCR attempt failed: {e_ocr}. Using direct text.")
                
                lines_on_page_with_numbers = []
                if current_page_raw_text:
                    for line_idx, line_content in enumerate(current_page_raw_text.split('\n')):
                        lines_on_page_with_numbers.append(f"P{page_num_1_indexed}.L{line_idx + 1}: {line_content}")
                
                page_full_text_with_lines = page_header + "\n" + "\n".join(lines_on_page_with_numbers)
                text_pages_with_line_numbers.append(page_full_text_with_lines)
            
            final_text = "\n\n=== End of Page / Start of Next Page ===\n\n".join(text_pages_with_line_numbers)
            # Remove the separator after the very last page
            if final_text.endswith("\n\n=== End of Page / Start of Next Page ===\n\n"):
                final_text = final_text[:-len("\n\n=== End of Page / Start of Next Page ===\n\n")]

        utils_logger.info(f"Successfully extracted and formatted approx {len(final_text)} characters from PDF.")
        return final_text

    except Exception as e:
        utils_logger.exception("Error extracting text from PDF")
        if pdf_data is not None:
             utils_logger.debug(f"   - Attempted to open data of type: {type(pdf_data)}")
        if "cannot open broken document" in str(e) or "syntax error" in str(e).lower():
             utils_logger.warning("   - Hint: The PDF file might be corrupted or not a standard PDF.")
        elif "permission error" in str(e).lower():
             utils_logger.warning("   - Hint: The PDF file might be password protected or have extraction restrictions.")
        elif isinstance(e, TypeError) and "bad stream" in str(e):
             utils_logger.warning(f"   - Type passed to fitz.open(stream=...) was: {type(pdf_data)}") 
        traceback.print_exc()
        return None


# --- LLM Prompt Construction (Refactored) ---
def construct_llm_prompt(abstract: Optional[str], criteria_full_text: str) -> Optional[Dict[str, str]]:
    if not abstract or not isinstance(abstract, str) or abstract.strip() == "":
        return None # No abstract, cannot proceed

    user_criteria = get_current_criteria_object()
    system_prompt = user_criteria.get('ai_system_prompt', DEFAULT_SYSTEM_PROMPT)
    # Assuming output instructions template contains {abstract} but not {criteria}
    output_instructions_template = user_criteria.get('ai_output_format_instructions', DEFAULT_OUTPUT_INSTRUCTIONS)

    # Construct the main body, placing criteria first, then the instructions referencing the abstract
    prompt_body = f"""{criteria_full_text.strip()}

{output_instructions_template.format(abstract=abstract.strip())}"""

    return {
        "system_prompt": system_prompt.strip(),
        "main_prompt": prompt_body
     }


# --- Unified API Calling Function (Adjusted) ---
def call_llm_api(prompt_data: Dict[str, str], provider_name: str, model_id: str, api_key: str, base_url: Optional[str] = None) -> Dict[str, str]:
    system_prompt = prompt_data.get("system_prompt")
    main_prompt = prompt_data.get("main_prompt")

    if not api_key: return {"label": "CONFIG_ERROR", "justification": f"API Key for {provider_name} missing."}
    if not main_prompt: return {"label": "PROMPT_ERROR", "justification": "Main prompt body is missing."}

    utils_logger.info(f"Calling {provider_name} model: {model_id} (Base: {base_url or 'default'})")

    if provider_name == "DeepSeek" or provider_name == "OpenAI_ChatGPT":
        return _call_openai_compatible_api(main_prompt, system_prompt, model_id, api_key, base_url, provider_name)
    elif provider_name == "Google_Gemini":
        # Prepend system prompt for Gemini compatibility
        full_prompt_for_gemini = f"{system_prompt}\n\n{main_prompt}" if system_prompt else main_prompt
        return _call_gemini_api(full_prompt_for_gemini, model_id, api_key)
    elif provider_name == "Anthropic_Claude":
        return _call_claude_api(main_prompt, system_prompt, model_id, api_key, base_url)
    else:
        return {"label": "CONFIG_ERROR", "justification": f"Unsupported provider: {provider_name}."}


def _parse_llm_response(message_content: str) -> Dict[str, str]:
    """
    Enhanced LLM response parser that supports multiple modern LLM response formats.
    
    Supports formats from OpenAI, Claude, Gemini, and other providers.
    """
    label, justification = "PARSE_ERROR", "Could not parse justification."
    
    # Clean the response content
    content = message_content.strip()
    
    # Try multiple label formats (in order of preference)
    label_patterns = [
        r"^\s*LABEL:\s*(INCLUDE|EXCLUDE|MAYBE)\s*$",  # Original format
        r"^\s*Decision:\s*(INCLUDE|EXCLUDE|MAYBE)\s*$",  # Decision format
        r"^\s*Result:\s*(INCLUDE|EXCLUDE|MAYBE)\s*$",  # Result format
        r"^\s*(INCLUDE|EXCLUDE|MAYBE)\s*$",  # Direct format
        r"^\s*\*\*(INCLUDE|EXCLUDE|MAYBE)\*\*\s*$",  # Markdown bold format
        r"(INCLUDE|EXCLUDE|MAYBE)",  # Any position (last resort)
    ]
    
    # Try multiple justification formats
    justification_patterns = [
        r"^\s*Justification:\s*(.+)$",  # Original format
        r"^\s*Reasoning:\s*(.+)$",  # Reasoning format
        r"^\s*Explanation:\s*(.+)$",  # Explanation format
        r"^\s*Because:\s*(.+)$",  # Because format
        r"^\s*Rationale:\s*(.+)$",  # Rationale format
        r"^\s*Analysis:\s*(.+)$",  # Analysis format
    ]
    
    # Find label
    for pattern in label_patterns:
        match = re.search(pattern, content, re.I | re.M)
        if match:
            label = match.group(1).upper()
            break
    
    # Find justification
    for pattern in justification_patterns:
        match = re.search(pattern, content, re.I | re.M | re.S)
        if match:
            justification = match.group(1).strip()
            break
    
    # If no justification found, try to extract content after label line
    if justification == "Could not parse justification." and label != "PARSE_ERROR":
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if any(re.search(pattern, line, re.I) for pattern in label_patterns):
                # Found label line, extract subsequent content
                remaining_lines = [l.strip() for l in lines[i+1:] if l.strip()]
                if remaining_lines:
                    justification = " ".join(remaining_lines)
                break
    
    # If still no justification, try to extract non-label content
    if justification == "Could not parse justification.":
        lines = content.splitlines()
        non_label_lines = []
        for line in lines:
            # Skip lines that contain only labels
            if not any(re.search(pattern, line, re.I) for pattern in label_patterns):
                if line.strip():
                    non_label_lines.append(line.strip())
        
        if non_label_lines:
            justification = " ".join(non_label_lines)
        elif label != "PARSE_ERROR":
            justification = f"Decision: {label} (no detailed reasoning provided)"
        else:
            justification = f"Raw response: {content[:200]}..."
    
    # Log parsing issues for debugging
    if label == "PARSE_ERROR":
        utils_logger.warning(f"Parse Error: Could not extract LABEL. Response snippet: '{content[:200]}...'")
    elif justification.startswith("Raw response:"):
        utils_logger.warning(f"Justification parsing issue for label {label}. Response: '{content[:100]}...'")
    
    return {"label": label, "justification": justification}


def _call_openai_compatible_api(main_prompt: str, system_prompt: Optional[str], model_id: str, api_key: str, base_url: str, provider_name: str) -> \
Dict[str, str]:
    # Get model-specific optimized configuration for screening
    model_config = get_optimized_parameters(provider_name, model_id, "screening")
    retry_strategy = get_retry_strategy(provider_name, model_id)
    
    # Build API endpoint
    api_endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    # Prepare messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": main_prompt})
    
    # Build request data with optimized parameters
    data = {
        "model": model_id,
        "messages": messages,
        "max_tokens": model_config.get("max_tokens", 200)
    }
    
    # Add temperature and top_p only if they are not None
    if model_config.get("temperature") is not None:
        data["temperature"] = model_config["temperature"]
    if model_config.get("top_p") is not None:
        data["top_p"] = model_config["top_p"]
    
    # Add provider-specific parameters
    if provider_name == "OpenAI_ChatGPT":
        data.update({
            "frequency_penalty": model_config.get("frequency_penalty", 0.0),
            "presence_penalty": model_config.get("presence_penalty", 0.0),
        })
        # Add seed for deterministic responses if specified
        if model_config.get("seed") is not None:
            data["seed"] = model_config["seed"]
    elif provider_name == "DeepSeek":
        # DeepSeek-specific parameters
        if model_id == "deepseek-reasoner":
            # For reasoning model, remove unsupported parameters
            data = {
                "model": model_id,
                "messages": messages,
                "max_tokens": model_config.get("max_tokens", 200)
            }
        else:
            # For deepseek-chat, use all parameters
            data.update({
                "frequency_penalty": model_config.get("frequency_penalty", 0.0),
                "presence_penalty": model_config.get("presence_penalty", 0.0),
            })
    
    # Special handling for DeepSeek R1 - use faster timeout for cloud deployment
    if provider_name == "DeepSeek" and model_id == "deepseek-reasoner":
        # Use shorter timeout to avoid network layer conflicts
        timeout_config = min(model_config.get("timeout", 30), 90)
    
    # Implement retry logic with exponential backoff
    max_retries = retry_strategy["max_retries"]
    base_delay = retry_strategy["retry_delay"]
    max_delay = retry_strategy["max_delay"]
    timeout_config = model_config.get("timeout", 30)
    
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(api_endpoint, headers=headers, json=data, timeout=timeout_config)
            response.raise_for_status()
            res_json = response.json()
            if res_json.get('choices') and res_json['choices'][0].get('message'):
                content = res_json['choices'][0]['message'].get('content', '')
                return _parse_llm_response(content)
            error_msg = res_json.get('error', {}).get('message', str(res_json))
            return {"label": "API_ERROR", "justification": f"{provider_name} API Error: {error_msg}"}
            
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                if retry_strategy.get("jitter", True):
                    delay *= (0.5 + random.random() * 0.5)  # Add jitter
                utils_logger.warning(f"{provider_name} timeout on attempt {attempt + 1}, retrying in {delay:.2f}s")
                time.sleep(delay)
                continue
            return {"label": "API_TIMEOUT", "justification": f"{provider_name} request timed out after {max_retries} retries."}
            
        except requests.exceptions.RequestException as e:
            status = e.response.status_code if e.response is not None else "N/A"
            
            # Handle rate limiting with exponential backoff
            if status == 429 or "rate limit" in str(e).lower():
                if attempt < max_retries:
                    # Extract retry-after header if available
                    retry_after = None
                    if e.response and 'retry-after' in e.response.headers:
                        try:
                            retry_after = int(e.response.headers['retry-after'])
                        except ValueError:
                            pass
                    
                    delay = retry_after if retry_after else min(base_delay * (2 ** attempt), max_delay)
                    if retry_strategy.get("jitter", True) and not retry_after:
                        delay *= (0.5 + random.random() * 0.5)  # Add jitter only if no retry-after
                    
                    utils_logger.warning(f"{provider_name} rate limited on attempt {attempt + 1}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
            
            # Enhanced network error handling for N/A status
            if e.response is None:
                error_type = type(e).__name__
                error_details = {
                    "ConnectionError": "网络连接失败 - 检查DNS/防火墙",
                    "SSLError": "SSL/TLS错误 - 检查证书配置", 
                    "Timeout": "网络超时 - 检查网络稳定性",
                    "ProxyError": "代理错误 - 检查代理配置"
                }
                
                diagnostic_msg = error_details.get(error_type, f"网络错误 ({error_type})")
                details = f"{diagnostic_msg}: {str(e)}"
                
                # 记录详细的网络诊断信息
                utils_logger.error(f"Network diagnostic - Provider: {provider_name}, Error: {error_type}, Details: {str(e)}")
                
                # 对于网络层面错误，使用更激进的重试
                if attempt < max_retries:
                    delay = min(base_delay * (3 ** attempt), 120)  # 指数退避，最多2分钟
                    utils_logger.warning(f"{provider_name} network error on attempt {attempt + 1}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
            else:
                details = str(e.response.text[:200])
                    
            return {"label": f"API_HTTP_ERROR_{status}", "justification": f"{provider_name} HTTP Error {status}: {details}"}
            
        except Exception as e:
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                if retry_strategy.get("jitter", True):
                    delay *= (0.5 + random.random() * 0.5)  # Add jitter
                utils_logger.warning(f"{provider_name} error on attempt {attempt + 1}, retrying in {delay:.2f}s: {str(e)}")
                time.sleep(delay)
                continue
            utils_logger.exception(f"Script error ({provider_name})")
            return {"label": "SCRIPT_ERROR", "justification": f"Script error ({provider_name}): {str(e)}"}


def _call_deepseek_r1_with_enhanced_timeout(api_endpoint: str, headers: Dict[str, str], data: Dict[str, Any], 
                                           retry_strategy: Dict[str, Any], model_config: Dict[str, Any]) -> Dict[str, str]:
    """
    Enhanced timeout handling specifically for DeepSeek R1 reasoning model.
    Implements multiple strategies to overcome network-level timeout limitations.
    """
    import socket
    import requests.adapters
    from urllib3.util.retry import Retry
    
    max_retries = retry_strategy["max_retries"]
    base_delay = retry_strategy["retry_delay"]
    max_delay = retry_strategy["max_delay"]
    
    # Strategy 1: Use separate connection and read timeouts
    connect_timeout = 30  # 30 seconds for connection
    read_timeout = 240    # 4 minutes for reading (reasoning takes time)
    
    utils_logger.info(f"DeepSeek R1: Using enhanced timeout strategy (connect: {connect_timeout}s, read: {read_timeout}s)")
    
    for attempt in range(max_retries + 1):
        try:
            # Strategy 2: Create custom session with optimized settings
            session = requests.Session()
            
            # Configure HTTP adapter with custom settings
            retry_config = Retry(
                total=0,  # We handle retries manually
                connect=0,
                read=0,
                backoff_factor=0,
                status_forcelist=[]
            )
            
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=1,
                pool_maxsize=1,
                max_retries=retry_config,
                socket_options=[
                    (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                    (socket.SOL_TCP, socket.TCP_KEEPIDLE, 60),
                    (socket.SOL_TCP, socket.TCP_KEEPINTVL, 30),
                    (socket.SOL_TCP, socket.TCP_KEEPCNT, 3)
                ]
            )
            
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            
            # Strategy 3: Use tuple timeout (connect_timeout, read_timeout)
            response = session.post(
                api_endpoint, 
                headers=headers, 
                json=data, 
                timeout=(connect_timeout, read_timeout),
                stream=False
            )
            
            response.raise_for_status()
            res_json = response.json()
            
            if res_json.get('choices') and res_json['choices'][0].get('message'):
                content = res_json['choices'][0]['message'].get('content', '')
                
                # Handle DeepSeek-R1 reasoning content
                if 'reasoning_content' in res_json['choices'][0]['message']:
                    reasoning_content = res_json['choices'][0]['message'].get('reasoning_content', '')
                    utils_logger.info(f"DeepSeek-R1 reasoning length: {len(reasoning_content)} chars")
                
                utils_logger.info(f"DeepSeek R1: Successfully completed on attempt {attempt + 1}")
                return _parse_llm_response(content)
            
            error_msg = res_json.get('error', {}).get('message', str(res_json))
            return {"label": "API_ERROR", "justification": f"DeepSeek R1 API Error: {error_msg}"}
            
        except requests.exceptions.Timeout as e:
            timeout_type = "connection" if "timed out" in str(e) and "connect" in str(e) else "read"
            utils_logger.warning(f"DeepSeek R1: {timeout_type} timeout on attempt {attempt + 1}")
            
            if attempt < max_retries:
                # Strategy 4: Adaptive timeout increase
                if timeout_type == "read":
                    read_timeout = min(read_timeout + 60, 360)  # Increase read timeout up to 6 minutes
                    utils_logger.info(f"DeepSeek R1: Increasing read timeout to {read_timeout}s for next attempt")
                
                delay = min(base_delay * (2 ** attempt), max_delay)
                if retry_strategy.get("jitter", True):
                    delay *= (0.5 + random.random() * 0.5)
                
                utils_logger.warning(f"DeepSeek R1: Retrying in {delay:.2f}s with enhanced timeout settings")
                time.sleep(delay)
                continue
            
            return {"label": "API_TIMEOUT", "justification": f"DeepSeek R1 {timeout_type} timeout after {max_retries} retries with enhanced timeout handling."}
            
        except requests.exceptions.RequestException as e:
            status = e.response.status_code if e.response is not None else "N/A"
            
            # Handle rate limiting
            if status == 429 or "rate limit" in str(e).lower():
                if attempt < max_retries:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    utils_logger.warning(f"DeepSeek R1: Rate limited on attempt {attempt + 1}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
            
            details = str(e.response.text[:200]) if e.response is not None else str(e)
            return {"label": f"API_HTTP_ERROR_{status}", "justification": f"DeepSeek R1 HTTP Error {status}: {details}"}
            
        except Exception as e:
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                utils_logger.warning(f"DeepSeek R1: Unexpected error on attempt {attempt + 1}, retrying in {delay:.2f}s: {str(e)}")
                time.sleep(delay)
                continue
            
            utils_logger.exception("DeepSeek R1: Script error")
            return {"label": "SCRIPT_ERROR", "justification": f"DeepSeek R1 script error after {max_retries} retries: {str(e)}"}
    
    return {"label": "API_TIMEOUT", "justification": "DeepSeek R1 failed after all retry attempts with enhanced timeout handling."}


def get_optimized_parameters(provider_name: str, model_id: str, task_type: str = "screening") -> Dict[str, Any]:
    """
    Get optimized parameters for a specific model and task type.
    
    Args:
        provider_name: Name of the LLM provider
        model_id: Model identifier
        task_type: Type of task (e.g., "screening", "extraction")
    
    Returns:
        Dictionary with optimized parameters
    """
    # Import here to avoid circular imports
    from config.config import get_model_specific_config
    
    # Get base configuration
    base_config = get_model_specific_config(provider_name, model_id)
    
    if not base_config:
        # Return default configuration if model not found
        return {
            "temperature": 0.1,
            "max_tokens": 200,
            "max_output_tokens": 200,
            "timeout": 30,
            "top_p": 0.8,
            "top_k": 40
        }
    
    # Create a copy to avoid modifying the original
    config = base_config.copy()
    
    # Apply task-specific optimizations
    if task_type == "screening":
        # Reduce temperature for more consistent screening results
        if config.get("temperature") is not None:
            config["temperature"] = max(0.0, config["temperature"] - 0.05)
        
        # Special handling for DeepSeek R1 reasoning model
        if provider_name == "DeepSeek" and model_id == "deepseek-reasoner":
            # Use the enhanced timeout settings directly for reasoning model
            config["timeout"] = config.get("timeout", 240)  # Keep the configured timeout
        else:
            # Standard timeout increase for other models
            current_timeout = config.get("timeout", 30)
            config["timeout"] = current_timeout + 10
        
        # Ensure we have reasonable defaults for screening
        config.setdefault("max_tokens", 200)
        config.setdefault("max_output_tokens", 200)
    
    return config


def get_retry_strategy(provider_name: str, model_id: str) -> Dict[str, Any]:
    """
    Get retry strategy configuration for a specific provider and model.
    
    Args:
        provider_name: Name of the LLM provider
        model_id: Model identifier
    
    Returns:
        Dictionary with retry strategy parameters
    """
    # Import here to avoid circular imports
    from config.config import get_model_specific_config
    
    # Get model-specific retry config
    model_config = get_model_specific_config(provider_name, model_id)
    
    # Default retry strategy
    default_strategy = {
        "max_retries": 3,
        "retry_delay": 2.0,
        "max_delay": 30.0,
        "jitter": True
    }
    
    # Override with model-specific settings if available
    if model_config:
        default_strategy.update({
            "max_retries": model_config.get("max_retries", 3),
            "retry_delay": model_config.get("retry_delay", 2.0),
            "max_delay": model_config.get("max_delay", 30.0),
            "jitter": model_config.get("jitter", True)
        })
    
    return default_strategy


def _call_gemini_api(full_prompt: str, model_id: str, api_key: str) -> Dict[str, str]:
    if genai is None:
        return {"label": "CONFIG_ERROR", "justification": "Google Gemini SDK not installed"}
    
    # Get model-specific optimized configuration for screening
    model_config = get_optimized_parameters("Google_Gemini", model_id, "screening")
    retry_strategy = get_retry_strategy("Google_Gemini", model_id)
    
    # Get safety settings from model config
    safety_settings = model_config.get("safety_settings", [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ])
    
    # Implement retry logic with exponential backoff
    max_retries = retry_strategy["max_retries"]
    base_delay = retry_strategy["retry_delay"]
    max_delay = retry_strategy["max_delay"]
    timeout_config = model_config.get("timeout", 30)
    
    for attempt in range(max_retries + 1):
        try:
            if GEMINI_SDK_VERSION == "new":
                # Use new Google Gen AI SDK with optimized parameters
                from google.genai import types
                client = genai.Client(api_key=api_key)
                
                # Convert safety settings to new SDK format
                new_safety_settings = []
                for setting in safety_settings:
                    new_safety_settings.append(
                        types.SafetySetting(
                            category=setting["category"], 
                            threshold=setting["threshold"]
                        )
                    )
                
                response = client.models.generate_content(
                    model=model_id,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=model_config.get("max_output_tokens", 200),
                        temperature=model_config.get("temperature", 0.1),
                        top_p=model_config.get("top_p", 0.8),
                        top_k=model_config.get("top_k", 40),
                        candidate_count=1,  # Always 1 for screening consistency
                        stop_sequences=model_config.get("stop_sequences", []),
                        safety_settings=new_safety_settings
                    )
                )
                if hasattr(response, 'text') and response.text:
                    return _parse_llm_response(response.text)
                else:
                    return {"label": "API_ERROR", "justification": "No text content in Gemini response"}
                    
            else:
                # Use legacy google.generativeai SDK with optimized parameters
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_id)
                config = genai.types.GenerationConfig(
                    max_output_tokens=model_config.get("max_output_tokens", 200), 
                    temperature=model_config.get("temperature", 0.1), 
                    top_p=model_config.get("top_p", 0.8),
                    top_k=model_config.get("top_k", 40),
                    candidate_count=1,  # Always 1 for screening consistency
                    stop_sequences=model_config.get("stop_sequences", [])
                )
                
                # Convert safety settings to legacy format
                legacy_safety = [{"category": s["category"], "threshold": s["threshold"]} for s in safety_settings]
                
                response = model.generate_content(
                    contents=[{"role": "user", "parts": [{"text": full_prompt}]}],
                    generation_config=config, 
                    safety_settings=legacy_safety
                )
                
                if response.parts:
                    content = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                    return _parse_llm_response(content)
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    return {"label": "API_BLOCKED",
                            "justification": f"Gemini content blocked: {response.prompt_feedback.block_reason}"}
                finish_reason = response.candidates[0].finish_reason.name if response.candidates and response.candidates[
                    0].finish_reason else "UNKNOWN"
                return {"label": f"API_{finish_reason}",
                        "justification": f"Gemini API no content, reason: {finish_reason}. Details: {str(response)[:200]}"}
                        
        except Exception as e:
            error_msg = str(e)
            
            # Handle rate limiting with exponential backoff
            if "quota" in error_msg.lower() or "rate limit" in error_msg.lower() or "429" in error_msg:
                if attempt < max_retries:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if retry_strategy.get("jitter", True):
                        delay *= (0.5 + random.random() * 0.5)  # Add jitter
                    utils_logger.warning(f"Gemini rate limited on attempt {attempt + 1}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
                return {"label": "API_QUOTA_ERROR", "justification": f"Gemini API quota/rate limit error after {max_retries} retries: {error_msg}"}
            
            # Handle timeout errors
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                if attempt < max_retries:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if retry_strategy.get("jitter", True):
                        delay *= (0.5 + random.random() * 0.5)  # Add jitter
                    utils_logger.warning(f"Gemini timeout on attempt {attempt + 1}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
                return {"label": "API_TIMEOUT", "justification": f"Gemini API timeout after {max_retries} retries: {error_msg}"}
            
            # Handle authentication errors (no retry)
            if "api key" in error_msg.lower() or "authentication" in error_msg.lower():
                return {"label": "API_AUTH_ERROR", "justification": f"Gemini API authentication error: {error_msg}"}
            
            # Handle other errors with retry
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                if retry_strategy.get("jitter", True):
                    delay *= (0.5 + random.random() * 0.5)  # Add jitter
                utils_logger.warning(f"Gemini error on attempt {attempt + 1}, retrying in {delay:.2f}s: {error_msg}")
                time.sleep(delay)
                continue
            
            utils_logger.exception("Gemini API error")
            return {"label": "GEMINI_API_ERROR", "justification": f"Gemini API error after {max_retries} retries: {error_msg}"}


def _call_claude_api(main_prompt: str, system_prompt: Optional[str], model_id: str, api_key: str, base_url: Optional[str] = None) -> Dict[str, str]:
    # Get model-specific optimized configuration for screening
    model_config = get_optimized_parameters("Anthropic_Claude", model_id, "screening")
    retry_strategy = get_retry_strategy("Anthropic_Claude", model_id)
    
    # Implement retry logic with exponential backoff
    max_retries = retry_strategy["max_retries"]
    base_delay = retry_strategy["retry_delay"]
    max_delay = retry_strategy["max_delay"]
    timeout_config = model_config.get("timeout", 30)
    
    for attempt in range(max_retries + 1):
        try:
            client = Anthropic(
                api_key=api_key,
                base_url=base_url or SUPPORTED_LLM_PROVIDERS["Anthropic_Claude"]["default_base_url"],
                timeout=timeout_config
            )
            effective_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT # Use default if none provided
            
            # Build request parameters with optimized settings
            request_params = {
                "model": model_id, 
                "max_tokens": model_config.get("max_tokens", 200), 
                "temperature": model_config.get("temperature", 0.1),
                "system": effective_system_prompt,
                "messages": [{"role": "user", "content": main_prompt}]
            }
            
            # Add Claude-specific parameters if available
            if model_config.get("top_p") is not None:
                request_params["top_p"] = model_config["top_p"]
            if model_config.get("top_k") is not None:
                request_params["top_k"] = model_config["top_k"]
            if model_config.get("stop_sequences"):
                request_params["stop_sequences"] = model_config["stop_sequences"]
            
            response = client.messages.create(**request_params)
            
            if response.content and response.content[0].type == "text":
                return _parse_llm_response(response.content[0].text)
            reason = response.stop_reason or 'unknown_format'
            if reason == "max_tokens": 
                return {"label": "API_MAX_TOKENS", "justification": "Claude output truncated (max_tokens)."}
            return {"label": "API_ERROR", "justification": f"Claude API Error ({reason}): {str(response)[:200]}"}
            
        except RateLimitError as e:
            if attempt < max_retries:
                # Extract retry-after from headers if available
                retry_after = None
                if hasattr(e, 'response') and e.response and hasattr(e.response, 'headers'):
                    retry_after_header = e.response.headers.get('retry-after') or e.response.headers.get('anthropic-ratelimit-requests-reset')
                    if retry_after_header:
                        try:
                            retry_after = int(retry_after_header)
                        except ValueError:
                            pass
                
                delay = retry_after if retry_after else min(base_delay * (2 ** attempt), max_delay)
                if retry_strategy.get("jitter", True) and not retry_after:
                    delay *= (0.5 + random.random() * 0.5)  # Add jitter only if no retry-after
                
                utils_logger.warning(f"Claude rate limited on attempt {attempt + 1}, retrying in {delay:.2f}s")
                time.sleep(delay)
                continue
            return {"label": "CLAUDE_RATE_LIMIT", "justification": f"Claude API rate limit exceeded after {max_retries} retries: {str(e)}"}
            
        except APIConnectionError as e:
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                if retry_strategy.get("jitter", True):
                    delay *= (0.5 + random.random() * 0.5)  # Add jitter
                utils_logger.warning(f"Claude connection error on attempt {attempt + 1}, retrying in {delay:.2f}s")
                time.sleep(delay)
                continue
            return {"label": "CLAUDE_CONNECTION_ERROR", "justification": f"Claude API connection error after {max_retries} retries: {str(e)}"}
            
        except APIStatusError as e:
            # Handle specific HTTP status codes
            if hasattr(e, 'status_code'):
                if e.status_code == 429:  # Rate limit
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        if retry_strategy.get("jitter", True):
                            delay *= (0.5 + random.random() * 0.5)  # Add jitter
                        utils_logger.warning(f"Claude 429 error on attempt {attempt + 1}, retrying in {delay:.2f}s")
                        time.sleep(delay)
                        continue
                elif e.status_code in [500, 502, 503, 504]:  # Server errors
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        if retry_strategy.get("jitter", True):
                            delay *= (0.5 + random.random() * 0.5)  # Add jitter
                        utils_logger.warning(f"Claude server error {e.status_code} on attempt {attempt + 1}, retrying in {delay:.2f}s")
                        time.sleep(delay)
                        continue
                elif e.status_code in [401, 403]:  # Auth errors (no retry)
                    return {"label": f"CLAUDE_AUTH_ERROR_{e.status_code}", "justification": f"Claude API authentication error: {str(e)}"}
            
            return {"label": f"CLAUDE_API_ERROR_{e.status_code if hasattr(e, 'status_code') else 'GENERAL'}", 
                    "justification": f"Claude API Error: {str(e)}"}
            
        except APIError as e:  # Catch other Anthropic errors
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                if retry_strategy.get("jitter", True):
                    delay *= (0.5 + random.random() * 0.5)  # Add jitter
                utils_logger.warning(f"Claude API error on attempt {attempt + 1}, retrying in {delay:.2f}s: {str(e)}")
                time.sleep(delay)
                continue
            return {"label": f"CLAUDE_API_ERROR_{e.status_code if hasattr(e, 'status_code') else 'GENERAL'}",
                    "justification": f"Claude API Error after {max_retries} retries: {str(e)}"}
            
        except Exception as e:
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                if retry_strategy.get("jitter", True):
                    delay *= (0.5 + random.random() * 0.5)  # Add jitter
                utils_logger.warning(f"Claude error on attempt {attempt + 1}, retrying in {delay:.2f}s: {str(e)}")
                time.sleep(delay)
                continue
            utils_logger.exception(f"Script error (Claude)")
            return {"label": "SCRIPT_ERROR", "justification": f"Script error (Claude) after {max_retries} retries: {str(e)}"}


# --- ADDED/REFINED: LLM API Call for Raw Content ---
def call_llm_api_raw_content(prompt_data: Dict[str, str], provider_name: str, model_id: str, api_key: str, base_url: Optional[str] = None, max_tokens_override: Optional[int] = None) -> Optional[str]:
    """Calls the appropriate LLM API and attempts to return the raw text content.
       Handles different provider specifics for system prompts and parameters.
    """
    system_prompt = prompt_data.get("system_prompt")
    main_prompt = prompt_data.get("main_prompt")
    # Use a default max_tokens suitable for potentially larger JSON outputs
    max_tokens = max_tokens_override or 1024 
    # Use lower temperature for more deterministic extraction
    temperature = 0.1 

    if not api_key: return "API_ERROR: API Key missing in call."
    if not main_prompt: return "API_ERROR: Main prompt body is missing."

    utils_logger.info(f"Calling {provider_name} (Raw Content) model: {model_id}, Max Tokens: {max_tokens}")

    raw_content = None
    error_info = None

    try:
        if provider_name == "DeepSeek" or provider_name == "OpenAI_ChatGPT":
            api_endpoint = f"{base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            messages = []
            if system_prompt: messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": main_prompt})
            data: Dict[str, Any] = {"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            # Check if model supports JSON mode (heuristic)
            if "1106" in model_id or "gpt-4" in model_id or "preview" in model_id or "-o" in model_id: 
                 data["response_format"] = { "type": "json_object" }
                 utils_logger.info("   - Requesting JSON mode from OpenAI compatible API.")

            response = requests.post(api_endpoint, headers=headers, json=data, timeout=180)
            response.raise_for_status()
            res_json = response.json()
            if res_json.get('choices') and res_json['choices'][0].get('message'):
                raw_content = res_json['choices'][0]['message'].get('content')
            else: error_info = f"No choices/message in response: {res_json}"

        elif provider_name == "Google_Gemini":
            # Import genai here to ensure it's available
            try:
                if GEMINI_SDK_VERSION == "new":
                    from google import genai as gemini_client
                else:
                    import google.generativeai as gemini_client
            except ImportError:
                error_info = "Google Gemini SDK not installed"
                gemini_client = None
            
            if gemini_client is None:
                error_info = "Google Gemini SDK not installed"
            else:
                full_prompt = f"{system_prompt}\n\n{main_prompt}" if system_prompt else main_prompt
                
                if GEMINI_SDK_VERSION == "new":
                    # Use new Google Gen AI SDK
                    from google.genai import types
                    client = gemini_client.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model=model_id,
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            max_output_tokens=max_tokens,
                            temperature=temperature,
                            safety_settings=[
                                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE")
                            ]
                        )
                    )
                    if hasattr(response, 'text') and response.text:
                        raw_content = response.text
                    else:
                        error_info = "No text content in Gemini response"
                        
                else:
                    # Use legacy google.generativeai SDK
                    gemini_client.configure(api_key=api_key)
                    model = gemini_client.GenerativeModel(model_id)
                    config = gemini_client.types.GenerationConfig(max_output_tokens=max_tokens, temperature=temperature)
                    safety = [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
                    
                    response = model.generate_content(contents=[{"role": "user", "parts": [{"text": full_prompt}]}], generation_config=config, safety_settings=safety)
                    
                    if response.parts: 
                        raw_content = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                    else: 
                        error_info = f"No parts in response. Finish Reason: {response.candidates[0].finish_reason.name if response.candidates else 'Unknown'}"
                    if response.prompt_feedback and response.prompt_feedback.block_reason: 
                        error_info = f"Prompt blocked: {response.prompt_feedback.block_reason}"

        elif provider_name == "Anthropic_Claude":
            # Use the optimized Claude API function with proper error handling
            try:
                # Get model-specific configuration
                model_config = get_optimized_parameters("Anthropic_Claude", model_id, "screening")
                timeout_config = model_config.get("timeout", 30)
                
                client = Anthropic(
                    api_key=api_key, 
                    base_url=base_url or SUPPORTED_LLM_PROVIDERS["Anthropic_Claude"]["default_base_url"],
                    timeout=timeout_config
                )
                
                # Build request parameters with optimized settings
                request_params = {
                    "model": model_id,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system_prompt or DEFAULT_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": main_prompt}]
                }
                
                # Add Claude-specific parameters if available
                if model_config.get("top_p") is not None:
                    request_params["top_p"] = model_config["top_p"]
                if model_config.get("top_k") is not None:
                    request_params["top_k"] = model_config["top_k"]
                if model_config.get("stop_sequences"):
                    request_params["stop_sequences"] = model_config["stop_sequences"]
                
                response = client.messages.create(**request_params)
                
                if response.content and response.content[0].type == "text": 
                    raw_content = response.content[0].text
                else: 
                    error_info = f"No text content. Stop reason: {response.stop_reason}"
                    
            except Exception as claude_error:
                # Handle Claude-specific errors more gracefully
                error_msg = str(claude_error)
                if "403" in error_msg or "forbidden" in error_msg.lower():
                    error_info = f"Claude API access forbidden. Check API key, account balance, and permissions: {error_msg}"
                elif "401" in error_msg or "unauthorized" in error_msg.lower():
                    error_info = f"Claude API authentication failed. Check API key: {error_msg}"
                elif "429" in error_msg or "rate limit" in error_msg.lower():
                    error_info = f"Claude API rate limit exceeded: {error_msg}"
                else:
                    error_info = f"Claude API error: {error_msg}"
        
        else:
            error_info = f"Unsupported provider for raw content: {provider_name}"

    except TimeoutError: error_info = f"{provider_name} request timed out."
    except requests.exceptions.Timeout: error_info = f"{provider_name} request timed out."
    except requests.exceptions.RequestException as e: status = e.response.status_code if e.response is not None else 'N/A'; details = str(e.response.text[:200]) if e.response is not None else str(e); error_info = f"{provider_name} HTTP Error {status}: {details}"
    except APIError as e: error_info = f"Claude API Error: {str(e)}" # Specific Claude error
    except Exception as e:
        error_info = f"Generic API call error ({provider_name}): {str(e)}"
        utils_logger.exception(f"Error in raw API call ({provider_name})")
        traceback.print_exc()

    if error_info:
        utils_logger.error(f"API Call Error: {error_info}")
        # Return the error message itself? Or None? Returning error helps debug.
        return f"API_ERROR: {error_info}"
        
    # utils_logger.debug(f"Raw LLM Output: {raw_content[:200]}...") # If re-enabling debug logging for this
    return raw_content

# --- QUALITY ASSURANCE AND MONITORING FUNCTIONS ---

def validate_screening_response(response: Dict[str, str], abstract: str = "") -> Dict[str, Any]:
    """
    Validate the quality of a screening response against defined criteria.
    
    Args:
        response: The parsed LLM response with 'label' and 'justification'
        abstract: The original abstract (for context validation)
    
    Returns:
        Dictionary with validation results and quality metrics
    """
    validation_config = QUALITY_ASSURANCE_CONFIG["response_validation"]
    
    validation_result = {
        "is_valid": True,
        "issues": [],
        "quality_score": 1.0,
        "metrics": {}
    }
    
    # Validate label format
    label = response.get("label", "")
    if label not in ["INCLUDE", "EXCLUDE", "MAYBE"]:
        validation_result["is_valid"] = False
        validation_result["issues"].append(f"Invalid label: '{label}'. Must be INCLUDE, EXCLUDE, or MAYBE.")
        validation_result["quality_score"] -= 0.5
    
    # Validate justification
    justification = response.get("justification", "")
    if not justification or len(justification.strip()) < validation_config["min_justification_length"]:
        validation_result["is_valid"] = False
        validation_result["issues"].append(f"Justification too short: {len(justification)} chars (min: {validation_config['min_justification_length']})")
        validation_result["quality_score"] -= 0.3
    
    if len(justification) > validation_config["max_justification_length"]:
        validation_result["issues"].append(f"Justification too long: {len(justification)} chars (max: {validation_config['max_justification_length']})")
        validation_result["quality_score"] -= 0.1
    
    # Check for generic/template responses
    generic_phrases = [
        "based on the abstract",
        "the study appears to",
        "this study seems to",
        "the abstract suggests"
    ]
    generic_count = sum(1 for phrase in generic_phrases if phrase.lower() in justification.lower())
    if generic_count > 2:
        validation_result["issues"].append("Justification appears generic or template-like")
        validation_result["quality_score"] -= 0.2
    
    # Calculate quality metrics
    validation_result["metrics"] = {
        "label_valid": label in ["INCLUDE", "EXCLUDE", "MAYBE"],
        "justification_length": len(justification),
        "justification_word_count": len(justification.split()),
        "generic_phrase_count": generic_count,
        "has_specific_reasoning": any(word in justification.lower() for word in ["because", "since", "due to", "given that", "as", "therefore"])
    }
    
    return validation_result

def track_api_performance(provider_name: str, model_id: str, response_time: float, 
                         token_usage: Dict[str, int] = None, error: str = None) -> None:
    """
    Track API performance metrics for monitoring and optimization.
    
    Args:
        provider_name: Name of the LLM provider
        model_id: Model identifier
        response_time: Response time in seconds
        token_usage: Dictionary with input/output token counts
        error: Error message if request failed
    """
    if not MONITORING_CONFIG["performance_metrics"]["track_response_time"]:
        return
    
    # Log performance metrics
    utils_logger.info(f"API Performance - Provider: {provider_name}, Model: {model_id}, "
                     f"Response Time: {response_time:.2f}s, Tokens: {token_usage}, Error: {error}")
    
    # Check alert thresholds
    alert_thresholds = MONITORING_CONFIG["alerting"]["alert_thresholds"]
    if response_time > alert_thresholds["response_time"]:
        utils_logger.warning(f"ALERT: Slow response time detected - {response_time:.2f}s > {alert_thresholds['response_time']}s")
    
    # Calculate cost if token usage provided
    if token_usage and MONITORING_CONFIG["performance_metrics"]["track_cost_per_request"]:
        estimated_cost = estimate_api_cost(provider_name, model_id, token_usage)
        # Use a reasonable default threshold if not specified
        cost_threshold = 0.01  # $0.01 per request
        if estimated_cost > cost_threshold:
            utils_logger.warning(f"ALERT: High cost per request - ${estimated_cost:.4f} > ${cost_threshold}")

def estimate_api_cost(provider_name: str, model_id: str, token_usage: Dict[str, int]) -> float:
    """
    Estimate the cost of an API call based on token usage.
    
    Args:
        provider_name: Name of the LLM provider
        model_id: Model identifier
        token_usage: Dictionary with 'input_tokens' and 'output_tokens'
    
    Returns:
        Estimated cost in USD
    """
    # Simplified cost estimation based on known pricing (May 2025)
    cost_per_1k_tokens = {
        "DeepSeek": {"input": 0.00027, "output": 0.0011},  # DeepSeek V3
        "OpenAI_ChatGPT": {
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4o": {"input": 0.0025, "output": 0.01},
            "default": {"input": 0.0015, "output": 0.006}
        },
        "Google_Gemini": {"input": 0.000075, "output": 0.0003},  # Gemini 1.5 Flash
        "Anthropic_Claude": {"input": 0.0008, "output": 0.004}   # Claude 3.5 Haiku
    }
    
    input_tokens = token_usage.get("input_tokens", 0)
    output_tokens = token_usage.get("output_tokens", 0)
    
    if provider_name == "OpenAI_ChatGPT" and model_id in cost_per_1k_tokens[provider_name]:
        rates = cost_per_1k_tokens[provider_name][model_id]
    elif provider_name in cost_per_1k_tokens:
        rates = cost_per_1k_tokens[provider_name]
        if isinstance(rates, dict) and "default" in rates:
            rates = rates["default"]
    else:
        return 0.0  # Unknown provider
    
    if isinstance(rates, dict) and "input" in rates:
        input_cost = (input_tokens / 1000) * rates["input"]
        output_cost = (output_tokens / 1000) * rates["output"]
        return input_cost + output_cost
    
    return 0.0

def optimize_batch_processing(provider_name: str, total_items: int, current_error_rate: float = 0.0) -> Dict[str, Any]:
    """
    Calculate optimal batch processing parameters based on provider capabilities and current performance.
    
    Args:
        provider_name: Name of the LLM provider
        total_items: Total number of items to process
        current_error_rate: Current error rate (0.0 to 1.0)
    
    Returns:
        Dictionary with optimized batch processing parameters
    """
    # Get model-specific rate limits
    model_config = get_model_specific_config(provider_name, "default")
    rate_limits = model_config.get("rate_limit", {})
    
    # Calculate base batch size
    base_batch_size = calculate_optimal_batch_size(provider_name, "default", total_items)
    
    # Adjust based on error rate
    max_error_rate = 0.05  # 5% error rate threshold
    if current_error_rate > max_error_rate:
        # Reduce batch size and concurrency if error rate is high
        adjusted_batch_size = max(2, int(base_batch_size * 0.5))
        adjusted_concurrency = max(1, int(BATCH_PROCESSING_CONFIG["concurrent_batches"] * 0.5))
        recommended_delay = 2.0  # Add delay between batches
    else:
        adjusted_batch_size = base_batch_size
        adjusted_concurrency = BATCH_PROCESSING_CONFIG["concurrent_batches"]
        recommended_delay = 0.5
    
    # Calculate estimated processing time
    rpm_limit = rate_limits.get("requests_per_minute")
    if rpm_limit:
        max_requests_per_second = rpm_limit / 60
        estimated_time_seconds = total_items / max_requests_per_second
    else:
        # Estimate based on typical response times
        avg_response_time = 2.0  # seconds
        estimated_time_seconds = (total_items / adjusted_concurrency) * avg_response_time
    
    return {
        "batch_size": adjusted_batch_size,
        "concurrent_requests": adjusted_concurrency,
        "delay_between_batches": recommended_delay,
        "estimated_time_minutes": estimated_time_seconds / 60,
        "rate_limit_info": rate_limits,
        "recommendations": _generate_batch_recommendations(provider_name, total_items, current_error_rate)
    }

def _generate_batch_recommendations(provider_name: str, total_items: int, error_rate: float) -> List[str]:
    """Generate specific recommendations for batch processing optimization."""
    recommendations = []
    
    if provider_name == "Anthropic_Claude":
        recommendations.append("Claude has strict rate limits (50 RPM for Tier 1). Consider upgrading tier or using multiple API keys.")
        if total_items > 100:
            recommendations.append("For large datasets with Claude, consider processing in smaller chunks over multiple sessions.")
    
    elif provider_name == "DeepSeek":
        recommendations.append("DeepSeek has no rate limits but may queue requests under high load. Monitor for keep-alive responses.")
        if total_items > 1000:
            recommendations.append("DeepSeek can handle high concurrency well. Consider increasing batch size for large datasets.")
    
    elif provider_name == "Google_Gemini":
        recommendations.append("Gemini has generous rate limits. Good choice for medium to large batch processing.")
        if total_items > 500:
            recommendations.append("Consider using Gemini 1.5 Flash for cost-effective batch processing.")
    
    elif provider_name == "OpenAI_ChatGPT":
        recommendations.append("OpenAI rate limits vary by tier. Monitor usage to avoid hitting limits.")
        if total_items > 200:
            recommendations.append("Consider using GPT-4o Mini for cost-effective screening tasks.")
    
    if error_rate > 0.05:
        recommendations.append(f"High error rate detected ({error_rate:.1%}). Consider reducing batch size and adding delays.")
    
    if total_items > 1000:
        recommendations.append("For very large datasets, consider implementing checkpointing to resume processing after interruptions.")
    
    return recommendations

def create_screening_summary_report(results: List[Dict[str, Any]], provider_name: str, model_id: str) -> Dict[str, Any]:
    """
    Create a comprehensive summary report of screening results.
    
    Args:
        results: List of screening results with validation and performance data
        provider_name: Name of the LLM provider used
        model_id: Model identifier used
    
    Returns:
        Dictionary with comprehensive summary statistics
    """
    if not results:
        return {"error": "No results to summarize"}
    
    total_items = len(results)
    
    # Count decisions
    decision_counts = {"INCLUDE": 0, "EXCLUDE": 0, "MAYBE": 0, "ERROR": 0}
    for result in results:
        label = result.get("label", "ERROR")
        decision_counts[label] = decision_counts.get(label, 0) + 1
    
    # Calculate performance metrics
    response_times = [r.get("response_time", 0) for r in results if r.get("response_time")]
    token_usage = {"input_tokens": 0, "output_tokens": 0}
    error_count = sum(1 for r in results if r.get("label", "").startswith("API_") or r.get("label", "") == "ERROR")
    
    for result in results:
        if result.get("token_usage"):
            token_usage["input_tokens"] += result["token_usage"].get("input_tokens", 0)
            token_usage["output_tokens"] += result["token_usage"].get("output_tokens", 0)
    
    # Calculate quality metrics
    validation_scores = [r.get("validation", {}).get("quality_score", 0) for r in results if r.get("validation")]
    avg_quality_score = sum(validation_scores) / len(validation_scores) if validation_scores else 0
    
    # Estimate total cost
    total_cost = estimate_api_cost(provider_name, model_id, token_usage)
    
    summary = {
        "processing_summary": {
            "total_items": total_items,
            "successful_items": total_items - error_count,
            "error_count": error_count,
            "error_rate": error_count / total_items if total_items > 0 else 0,
            "provider": provider_name,
            "model": model_id
        },
        "decision_distribution": decision_counts,
        "decision_percentages": {
            k: (v / total_items * 100) if total_items > 0 else 0 
            for k, v in decision_counts.items()
        },
        "performance_metrics": {
            "avg_response_time": sum(response_times) / len(response_times) if response_times else 0,
            "min_response_time": min(response_times) if response_times else 0,
            "max_response_time": max(response_times) if response_times else 0,
            "total_tokens": token_usage["input_tokens"] + token_usage["output_tokens"],
            "input_tokens": token_usage["input_tokens"],
            "output_tokens": token_usage["output_tokens"],
            "estimated_cost_usd": total_cost
        },
        "quality_metrics": {
            "avg_quality_score": avg_quality_score,
            "validation_issues": sum(len(r.get("validation", {}).get("issues", [])) for r in results),
            "consistency_score": _calculate_consistency_score(results)
        },
        "recommendations": _generate_summary_recommendations(decision_counts, error_count / total_items if total_items > 0 else 0, avg_quality_score)
    }
    
    return summary

def _calculate_consistency_score(results: List[Dict[str, Any]]) -> float:
    """Calculate a consistency score based on response patterns."""
    if len(results) < 2:
        return 1.0
    
    # Simple consistency check based on justification length variance
    justification_lengths = [
        len(r.get("justification", "")) for r in results 
        if r.get("justification") and not r.get("label", "").startswith("API_")
    ]
    
    if len(justification_lengths) < 2:
        return 1.0
    
    # Calculate coefficient of variation (lower is more consistent)
    mean_length = sum(justification_lengths) / len(justification_lengths)
    variance = sum((x - mean_length) ** 2 for x in justification_lengths) / len(justification_lengths)
    std_dev = variance ** 0.5
    
    if mean_length == 0:
        return 1.0
    
    cv = std_dev / mean_length
    # Convert to consistency score (1.0 = perfectly consistent, 0.0 = highly inconsistent)
    consistency_score = max(0.0, 1.0 - cv)
    
    return consistency_score

def _generate_summary_recommendations(decision_counts: Dict[str, int], error_rate: float, quality_score: float) -> List[str]:
    """Generate recommendations based on screening results."""
    recommendations = []
    
    total_decisions = sum(decision_counts.values())
    if total_decisions == 0:
        return ["No valid decisions to analyze"]
    
    # Analyze decision distribution
    include_rate = decision_counts.get("INCLUDE", 0) / total_decisions
    exclude_rate = decision_counts.get("EXCLUDE", 0) / total_decisions
    maybe_rate = decision_counts.get("MAYBE", 0) / total_decisions
    
    if include_rate > 0.8:
        recommendations.append("High inclusion rate (>80%). Consider reviewing inclusion criteria for specificity.")
    elif include_rate < 0.05:
        recommendations.append("Very low inclusion rate (<5%). Consider reviewing criteria for potential over-exclusion.")
    
    if maybe_rate > 0.3:
        recommendations.append("High 'MAYBE' rate (>30%). Consider refining criteria or providing more specific guidance.")
    
    if error_rate > 0.1:
        recommendations.append(f"High error rate ({error_rate:.1%}). Consider switching providers or adjusting rate limits.")
    
    if quality_score < 0.7:
        recommendations.append(f"Low quality score ({quality_score:.2f}). Consider adjusting prompts or model parameters.")
    
    if quality_score > 0.95:
        recommendations.append("Excellent quality score. Current configuration is working well.")
    
    return recommendations