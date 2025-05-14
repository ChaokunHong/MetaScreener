import rispy
import pandas as pd
from typing import List, Dict, Optional, IO, Union, Any
import requests
import json
import re
import traceback
import io
import fitz # PyMuPDF
import pytesseract # <--- 新增导入
from PIL import Image # <--- 新增导入
import logging # <-- Import logging

# For Gemini
import google.generativeai as genai

# For Anthropic
from anthropic import Anthropic, APIStatusError, APIConnectionError, RateLimitError, APIError

# Import necessary items from config
from config import (
    SUPPORTED_LLM_PROVIDERS, # PICOT_TEMPLATE, # Ensure this is commented out or removed
    DEFAULT_SYSTEM_PROMPT, DEFAULT_OUTPUT_INSTRUCTIONS,
    get_screening_criteria, get_current_criteria_object,
    get_supported_criteria_frameworks, get_default_criteria_for_framework, get_current_framework_id,
    TESSERACT_CMD_PATH, PDF_OCR_THRESHOLD_CHARS
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
    label, justification = "PARSE_ERROR", "Could not parse justification."
    label_match = re.search(r"^\s*LABEL:\s*(INCLUDE|EXCLUDE|MAYBE)\s*$", message_content, re.I | re.M)
    just_match = re.search(r"^\s*Justification:\s*(.*)$", message_content,
                           re.I | re.M | re.S)  # re.S for multiline justification

    if label_match:
        label = label_match.group(1).upper()
        if just_match:
            justification = just_match.group(1).strip()
        else:  # Try to grab text after label line if "Justification:" prefix is missing
            lines = message_content.splitlines()
            try:
                label_line_idx = next(i for i, line in enumerate(lines) if re.match(r"^\s*LABEL:\s*", line, re.I))
                just_lines = [line.strip() for line in lines[label_line_idx + 1:] if line.strip()]
                if just_lines:
                    justification = " ".join(just_lines)
                else:
                    justification = "Justification missing or not formatted after LABEL."
            except StopIteration:  # Should not happen if label_match was successful
                justification = "Justification format error after LABEL."
    elif "INCLUDE" in message_content.upper():
        label = "INCLUDE"  # Basic fallback
    elif "EXCLUDE" in message_content.upper():
        label = "EXCLUDE"
    elif "MAYBE" in message_content.upper():
        label = "MAYBE"

    if label == "PARSE_ERROR":
        utils_logger.warning(f"Parse Error: Could not extract LABEL. Response snippet: '{message_content[:200]}...'")
        justification = f"Original unparsed response: {message_content[:200]}..."
    return {"label": label, "justification": justification}


def _call_openai_compatible_api(main_prompt: str, system_prompt: Optional[str], model_id: str, api_key: str, base_url: str, provider_name: str) -> \
Dict[str, str]:
    api_endpoint = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    else: # Add a default minimal system message if none provided
         messages.append({"role": "system", "content": "You are a helpful assistant performing literature screening."}) # Slightly more specific default
    messages.append({"role": "user", "content": main_prompt}) # Main prompt as user message
    data = {"model": model_id, "messages": messages, "temperature": 0.2, "max_tokens": 200, "top_p": 0.9}
    try:
        response = requests.post(api_endpoint, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        res_json = response.json()
        if res_json.get('choices') and res_json['choices'][0].get('message'):
            content = res_json['choices'][0]['message'].get('content', '')
            return _parse_llm_response(content)
        error_msg = res_json.get('error', {}).get('message', str(res_json))
        return {"label": "API_ERROR", "justification": f"{provider_name} API Error: {error_msg}"}
    except requests.exceptions.Timeout:
        return {"label": "API_TIMEOUT", "justification": f"{provider_name} request timed out."}
    except requests.exceptions.RequestException as e:
        status = e.response.status_code if e.response is not None else "N/A"
        details = str(e.response.text[:200]) if e.response is not None else str(e)
        return {"label": f"API_HTTP_ERROR_{status}", "justification": f"{provider_name} HTTP Error {status}: {details}"}
    except Exception as e:
        utils_logger.exception(f"Script error ({provider_name})")
        return {"label": "SCRIPT_ERROR", "justification": f"Script error ({provider_name}): {str(e)}"}


def _call_gemini_api(full_prompt: str, model_id: str, api_key: str) -> Dict[str, str]:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_id)
        config = genai.types.GenerationConfig(max_output_tokens=200, temperature=0.2, top_p=0.9)
        safety = [{"category": c, "threshold": "BLOCK_NONE"} for c in
                  ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                   "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        response = model.generate_content(contents=[{"role": "user", "parts": [{"text": full_prompt}]}],
                                          generation_config=config, safety_settings=safety)
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
        utils_logger.exception("Gemini API error")
        return {"label": "GEMINI_API_ERROR", "justification": f"Gemini API error: {str(e)}"}


def _call_claude_api(main_prompt: str, system_prompt: Optional[str], model_id: str, api_key: str, base_url: Optional[str] = None) -> Dict[str, str]:
    try:
        client = Anthropic(api_key=api_key,
                           base_url=base_url or SUPPORTED_LLM_PROVIDERS["Anthropic_Claude"]["default_base_url"])
        effective_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT # Use default if none provided
        response = client.messages.create(
             model=model_id, max_tokens=200, temperature=0.2,
             system=effective_system_prompt, # Pass system prompt here
             messages=[{"role": "user", "content": main_prompt}]
         )
        if response.content and response.content[0].type == "text":
            return _parse_llm_response(response.content[0].text)
        reason = response.stop_reason or 'unknown_format'
        if reason == "max_tokens": return {"label": "API_MAX_TOKENS",
                                           "justification": "Claude output truncated (max_tokens)."}
        return {"label": "API_ERROR", "justification": f"Claude API Error ({reason}): {str(response)[:200]}"}
    except APIError as e:  # Catch specific Anthropic errors
        return {"label": f"CLAUDE_API_ERROR_{e.status_code if hasattr(e, 'status_code') else 'GENERAL'}",
                "justification": f"Claude API Error: {str(e)}"}
    except Exception as e:
        utils_logger.exception(f"Script error (Claude)")
        return {"label": "SCRIPT_ERROR", "justification": f"Script error (Claude): {str(e)}"}


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
            genai.configure(api_key=api_key)
            # Newer Gemini models might support JSON mode via GenerationConfig
            # Check documentation for specific model_id capabilities.
            # For now, rely on prompt instructions.
            model = genai.GenerativeModel(model_id)
            config = genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=temperature)
            safety = [{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
            full_prompt = f"{system_prompt}\n\n{main_prompt}" if system_prompt else main_prompt
            response = model.generate_content(contents=[{"role": "user", "parts": [{"text": full_prompt}]}], generation_config=config, safety_settings=safety)
            if response.parts: raw_content = "".join(part.text for part in response.parts if hasattr(part, 'text'))
            else: error_info = f"No parts in response. Finish Reason: {response.candidates[0].finish_reason.name if response.candidates else 'Unknown'}"
            if response.prompt_feedback and response.prompt_feedback.block_reason: error_info = f"Prompt blocked: {response.prompt_feedback.block_reason}"

        elif provider_name == "Anthropic_Claude":
            client = Anthropic(api_key=api_key, base_url=base_url or SUPPORTED_LLM_PROVIDERS["Anthropic_Claude"]["default_base_url"])
            # Claude doesn't have explicit JSON mode via API param AFAIK, rely on prompt.
            response = client.messages.create(
                 model=model_id, max_tokens=max_tokens, temperature=temperature,
                 system=system_prompt or DEFAULT_SYSTEM_PROMPT, 
                 messages=[{"role": "user", "content": main_prompt}]
             )
            if response.content and response.content[0].type == "text": raw_content = response.content[0].text
            else: error_info = f"No text content. Stop reason: {response.stop_reason}"
        
        else:
            error_info = f"Unsupported provider for raw content: {provider_name}"

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