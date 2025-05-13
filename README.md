# MetaScreener: AI-Assisted Literature Screening

MetaScreener is a web application designed to streamline the literature screening process for systematic reviews, particularly in the medical field, using Large Language Models (LLMs). It helps researchers efficiently filter large volumes of abstracts (from RIS files) and full-text documents (PDFs) based on user-defined inclusion and exclusion criteria. The application supports various LLM providers and emphasizes secure, session-based API key handling.

**Live Application (Primary Deployment):** [https://www.metascreener.net/](https://www.metascreener.net/) (Typically reflects the latest stable version on Tencent Cloud).
**Alternative Deployment (May be used for testing/staging):** [https://metascreener.onrender.com](https://metascreener.onrender.com) (This Render instance may be outdated or experimental).

## ✨ Features

*   **Flexible Input Formats**:
    *   Upload `.ris` files for abstract screening.
    *   Upload single PDFs for individual full-text screening.
    *   **NEW**: Upload multiple PDFs for batch full-text screening.
*   **Configurable LLM Providers**: 
    *   Choose from DeepSeek, OpenAI (ChatGPT), Google (Gemini), and Anthropic (Claude).
    *   Select specific models from each provider.
*   **Secure API Key Management**: 
    *   User-provided API keys are stored *only* in the browser session for the current visit.
    *   Clear guidance and links for obtaining API keys.
    *   Option to clear stored session keys individually per provider.
*   **Advanced PDF Text Extraction**:
    *   Utilizes PyMuPDF for fast and accurate text extraction from text-based PDFs.
    *   Integrated OCR (Tesseract) fallback for scanned or image-based PDFs.
    *   Extracted text for LLM processing now includes page and line number context (e.g., `P1.L5: ...`).
    *   Attempts to extract document titles from PDF metadata for better display.
*   **Comprehensive Screening Criteria**: 
    *   Define detailed inclusion/exclusion criteria using the structured PICOT framework.
    *   Separate fields for **Include**, **Exclude**, and **Maybe** conditions for each PICOT element.
    *   Advanced options to customize the AI System Prompt and Output Format Instructions.
*   **Screening Modes & Workflow**:
    *   **Abstract Screening (RIS files)**:
        *   Filter by title keywords or line number range within the RIS file.
        *   Test Screening: Process a sample of abstracts with real-time progress (SSE) and detailed performance metrics (Accuracy, Kappa, Confusion Matrix, etc.) after manual assessment.
        *   Full Dataset Screening: Process all abstracts with real-time SSE progress.
    *   **Full-Text PDF Screening**:
        *   Single PDF: Upload, screen, view results with extracted text preview and original PDF preview using `pdf.js`.
        *   Batch PDF: Upload multiple PDFs, filter by filename or upload order, and process concurrently with SSE progress updates.
    *   **Data Extraction (Beta)**: Define custom fields and instructions to extract structured data from single PDFs.
*   **User Experience Enhancements**:
    *   Dedicated landing page (Hero section) for a professional introduction.
    *   Improved navigation with active link highlighting and consistent branding.
    *   Preview list for batch PDF uploads, allowing removal of individual files or clearing all selections before processing (with item numbering).
    *   Clear ("x") buttons for filter input fields.
    *   Expand/Collapse functionality for long abstract texts in results tables.
    *   Batch PDF screening results include a statistical summary of decisions.
*   **Result Download**: 
    *   Download abstract screening results (RIS) in CSV, Excel, or JSON formats.
    *   Download batch PDF screening results in CSV, Excel, or JSON formats.
*   **Performance**: Utilizes threading (`ThreadPoolExecutor`) for concurrent LLM API calls to speed up batch processing.
*   **Deployment-Ready**: Configured for Gunicorn and includes considerations for various deployment environments.

## 💻 Technology Stack

*   **Backend**: Python, Flask, Gunicorn
*   **Frontend**: HTML5, CSS3 (Bootstrap 4), JavaScript (including `pdf.js` for PDF rendering)
*   **LLM Integration**: Provider-specific Python SDKs (`requests`, `google-generativeai`, `anthropic`)
*   **Data Handling & Processing**: `pandas`, `rispy` (for .ris files)
*   **PDF Processing**: `PyMuPDF (fitz)` for text and metadata extraction, `Pytesseract` & `Pillow` for OCR.
*   **Task Scheduling (Internal Cleanup)**: `APScheduler`
*   **Metrics & Utilities**: `scikit-learn`, `cachetools`
*   **Deployment Platform Examples**: Tencent Cloud (manual Nginx/Gunicorn setup), Render.com (PaaS)

## 🚀 Getting Started (Local Setup)

Follow these instructions to set up and run the project locally for development or testing.

**Prerequisites:**

*   Python (3.10+ recommended)
*   `pip` (Python package installer)
*   Git
*   **Tesseract OCR Engine**: Required for PDF text extraction with OCR fallback.
    *   **Ubuntu/Debian**: `sudo apt-get update && sudo apt-get install tesseract-ocr tesseract-ocr-eng` (and other languages like `tesseract-ocr-chi-sim` if needed).
    *   **macOS (using Homebrew)**: `brew install tesseract tesseract-lang`
    *   **Windows**: Download installer from the official Tesseract GitHub page.
    *   Ensure the Tesseract command-line tool is in your system's PATH, or set the `TESSERACT_CMD_PATH` environment variable (see below).

**Setup:**

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url> # Replace with your actual repo URL
    cd MetaScreener # Or your project directory name
    ```

2.  **Create and activate a virtual environment:**
    *   On macOS/Linux:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    *   On Windows:
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables (Configuration):**
    *   Create a file named `.env` in the project root directory (e.g., `MetaScreener/.env`).
    *   Add necessary configurations. **Do not commit the `.env` file to Git.** Example:
        ```dotenv
        # --- LLM API Keys (Optional - can also be set only in UI session) ---
        # DEEPSEEK_API_KEY=sk-your_deepseek_key_here
        # OPENAI_API_KEY=sk-your_openai_key_here
        # GEMINI_API_KEY=AIz...your_gemini_key_here
        # ANTHROPIC_API_KEY=sk-ant-...your_claude_key_here

        # --- Flask Specific (Optional but recommended for dev) ---
        # SECRET_KEY=a_very_strong_random_string_for_flask_session # For session security
        # FLASK_DEBUG=1 # To run in debug mode via `flask run` (set FLASK_APP=app.py)

        # --- Tesseract OCR Configuration (Optional) ---
        # TESSERACT_CMD_PATH=/usr/bin/tesseract # Example for Linux, adjust to your Tesseract path if not in system PATH
        # PDF_OCR_THRESHOLD_CHARS=50 # Min chars on page to skip OCR (default 50 in config.py)
        
        # --- Log Level (Optional) ---
        # LOGLEVEL=DEBUG # For more verbose logging (INFO is default in app.py)
        ```
    *   **Note on API Keys**: While API keys can be set in `.env` for local testing convenience, the primary and recommended way for users to provide keys is through the LLM Configuration UI, which stores them securely in the browser session.

5.  **Run the development server:**
    *   Using Flask's built-in server (good for development):
        ```bash
        # Ensure FLASK_APP is set, e.g., export FLASK_APP=app.py (Linux/macOS) or set FLASK_APP=app.py (Windows)
        flask run --host=0.0.0.0 --port=5050 
        ```
        Or, if you have `if __name__ == '__main__': app.run(...)` in your `app.py`:
        ```bash
        python app.py
        ```
    The application should be available at `http://127.0.0.1:5050`.

## 📖 Usage Workflow

MetaScreener provides a step-by-step process for literature screening:

1.  **Landing Page (Home)**:
    *   Upon first visit, you'll see an overview of MetaScreener's capabilities.
    *   Use the main action buttons to navigate to "Configure LLM & Start" or directly to "View Screening Actions."

2.  **LLM Configuration (`/llm_config`)**:
    *   Select your desired LLM Provider and Model.
    *   Enter your API key for the selected provider. The status of the key (Not set, Using environment default, Set in session) will be displayed.
    *   You can view/hide the entered key.
    *   If a key is set in the session, a "Clear Key" button will appear to remove it from the current browser session.
    *   Click "Save LLM Config & API Key" to save your choices and any entered API key to the session.

3.  **Screening Criteria (`/criteria`)**:
    *   Define your study's inclusion and exclusion criteria using the PICOT framework.
    *   For each PICOT element, provide conditions for **Include**, **Exclude**, and **Maybe** classifications.
    *   Optionally, use the "Advanced Mode" to customize the AI System Prompt and Output Format Instructions.
    *   Save your criteria. You can also reset to default example criteria.

4.  **Screening Actions Dashboard (`/screening_actions`)**:
    *   This page provides links to the different screening modules.

5.  **Abstract Screening (`/abstract_screening`)**:
    *   Upload a `.ris` file.
    *   Optionally filter abstracts by title keywords or line number range (clearable inputs).
    *   Perform Test Screening on a sample with SSE progress and view detailed performance metrics.
    *   Perform Full Dataset Screening with SSE progress, view results (with expandable abstracts), and download.

6.  **Full-Text PDF Screening (`/full_text_screening`)**:
    *   **Single PDF**: Upload, screen, view results with extracted text (page/line numbered, OCR fallback), and an interactive original PDF preview.
    *   **Batch PDF**: Upload multiple PDFs, preview/remove selected files (with numbering), filter by filename or upload order (clearable inputs), process concurrently with SSE progress, view batch results (with decision stats, title extraction, ordered by upload), and download.

7.  **Data Extraction (Beta) (`/data_extraction`)**:
    *   Define custom fields to extract specific data points from a single PDF.

## ⚙️ Configuration Summary

*   **API Keys**: Primarily managed via the "LLM Configuration" UI (session storage). Can be pre-set in `.env` for local testing.
*   **Screening Criteria**: Defined via the "Screening Criteria" UI.
*   **Environment Variables for Advanced Config**: `TESSERACT_CMD_PATH`, `PDF_OCR_THRESHOLD_CHARS`, `LOGLEVEL` can be set in `.env` or system-wide to override defaults in `config.py`.

## ☁️ Deployment

This application can be deployed on various platforms.

**Primary Deployment (Tencent Cloud - `https://www.metascreener.net/`)**:
*   The live application is typically hosted on a Tencent Cloud server.
*   This setup usually involves **Nginx** as a reverse proxy and **Gunicorn** as the WSGI server.
*   **Manual Server Configuration Required**:
    *   Ensure Nginx is configured to proxy requests to Gunicorn (e.g., `proxy_pass http://127.0.0.1:5000;`).
    *   **Crucially, Nginx's `client_max_body_size` directive must be set to an appropriate value (e.g., `50M` or `100M`)** in your Nginx site configuration to allow for large PDF uploads. Without this, you will encounter "413 Request Entity Too Large" errors.
    *   Gunicorn should be run as a service (e.g., using `systemd`) for resilience. Example Gunicorn command: `gunicorn --workers 3 --bind 127.0.0.1:5000 app:app` (adjust worker count as needed).
    *   Firewall/Security Group rules on Tencent Cloud must allow traffic on HTTP (80) and HTTPS (443) ports.
    *   SSL/TLS certificates (e.g., from Let's Encrypt) should be configured in Nginx.

**Alternative Deployment (Render.com)**:
*   The application is also configured for easy deployment on [Render](https://render.com/).
*   It uses `gunicorn` as the WSGI server (start command on Render is typically: `gunicorn --workers 4 --bind 0.0.0.0:$PORT app:app`).
*   Required environment variables (as listed in the `.env` setup, excluding API keys if users provide them via UI) must be set in the Render service environment settings.
*   Render typically handles aspects like SSL and request routing automatically, but check their documentation for request body size limits if encountering issues.


## ⚙️ Running for Production (General Gunicorn Notes)

For a more robust setup, especially in production, use Gunicorn:

```bash
# Ensure your virtual environment is activated
# source venv/bin/activate

gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
```
*   `--workers 3`: Adjust the number of worker processes based on your server's CPU cores (e.g., `2 * num_cores + 1`).
*   `--bind 0.0.0.0:5000`: Listen on all interfaces on port 5000. Change as needed.
*   **Nginx Configuration**: As mentioned above, running Gunicorn behind Nginx is highly recommended.
*   **APScheduler with Multiple Workers**: If using multiple Gunicorn workers, the default APScheduler setup (running in each app instance) will cause the `cleanup_expired_pdf_files` job to run on each worker. For a simple daily cleanup of old files, this might be acceptable (as deleting an already-deleted file is harmless), but for critical, once-only tasks, a persistent job store for APScheduler or a dedicated scheduler process would be more robust.

## ⚠️ Important Notes

*   **API Key Security**: API keys are handled client-side (session storage) and are not stored on the server backend beyond the active user session.
*   **File Management & Cleanup**:
    *   PDFs uploaded for **batch full-text screening** are saved temporarily during processing (`uploads/batch_processing_*`) and are **automatically deleted** by their respective worker threads after processing is complete (or on error).
    *   PDFs uploaded for **single full-text screening** (which enables PDF preview) are saved in the `uploads/` directory (e.g., `uploads/<uuid>_<original_filename>.pdf`). Their metadata is managed by an in-memory cache (`TTLCache`) with a default Time-To-Live of 2 hours. While the cache entry expires, the actual file on disk is **not automatically deleted by the application itself through this cache expiration**.
    *   **Action Required for Single-Preview PDFs**: You **must** implement a strategy to periodically clean the `uploads/` directory of these single-preview PDF files. The built-in `APScheduler` job (`cleanup_expired_pdf_files`) is designed to do this by checking if the file's ID is still in the `TTLCache`. Ensure the scheduler is running and correctly configured for your deployment. As a fallback or alternative, a cron job can be used. Example for Linux (deletes matching files older than 7 days):
        ```cron
        0 3 * * * /usr/bin/find /path/to/your/MetaScreener/uploads -name "????????-????-????-????-????????????_*.pdf" -type f -mtime +7 -delete
        ```
        Replace `/path/to/your/MetaScreener/uploads` with the actual absolute path.
*   **Tesseract OCR**: For scanned PDF processing, Tesseract OCR must be installed on the server where the application is running. If it's not found in the system PATH, you must set the `TESSERACT_CMD_PATH` environment variable.

## 👨‍🔬 Author & Feedback

MetaScreener was developed by:

*   **Chaokun Hong**
*   chaokun.hong@ndm.ox.ac.uk
*   Centre for Tropical Medicine and Global Health, Nuffield Department of Medicine, University of Oxford, UK.

We welcome feedback, bug reports, and especially data on the performance (e.g., sensitivity, specificity, time saved) of MetaScreener in your literature screening workflows. Your real-world usage data is invaluable for improving this tool!

Please report issues or provide feedback via [GitHub Issues](https://github.com/ChaokunHong/MetaScreener/issues) (replace with your actual repository URL if different) or by contacting the author directly.

## ⚖️ Disclaimer

MetaScreener is provided "as-is" without any warranties of any kind, express or implied. The accuracy of AI-driven screening and data extraction heavily depends on the chosen LLM, the quality of the input data, and the clarity of the defined criteria. Users are solely responsible for verifying all results and making final decisions. The developers assume no liability for any outcomes resulting from the use of this software. Please use responsibly and in accordance with all applicable ethical guidelines and institutional policies.

---

