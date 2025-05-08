# MetaScreener: AI-Assisted Literature Screening

MetaScreener is a web application designed to streamline the literature screening process for systematic reviews, particularly in the medical field, using Large Language Models (LLMs). It helps researchers efficiently filter large volumes of abstracts based on predefined inclusion and exclusion criteria, and extract key data points from full-text documents.

**Live Application:** [https://metascreener.onrender.com](https://metascreener.onrender.com)

## ✨ Features

*   **RIS File Upload**: Supports uploading citation library files in `.ris` format for abstract screening.
*   **PDF Upload**: Supports uploading single PDF documents for full-text screening and data extraction.
*   **Configurable LLM**: Choose from major LLM providers and models:
    *   DeepSeek (Chat, Reasoner)
    *   OpenAI (GPT-3.5 Turbo, GPT-4, GPT-4 Turbo, GPT-4o)
    *   Google Gemini (1.0 Pro, 1.5 Pro, 1.5 Flash)
    *   Anthropic Claude (Haiku, Sonnet, Opus, 2.1)
*   **Secure API Key Handling**: Requires user-provided API keys stored *only* in the browser session for the duration of the visit (not recorded server-side). Links provided for obtaining keys.
*   **Structured Screening Criteria**: Define detailed criteria using the PICOT framework, with specific fields for **Include**, **Exclude**, and **Maybe** conditions for each element (Population, Intervention, Comparison, Outcome, Time/Type).
*   **AI Prompt Customization (Advanced)**: Advanced users can modify the underlying System Prompt and Output Format Instructions sent to the LLM.
*   **Guided Input**: Hints and placeholders guide users in formulating effective criteria.
*   **Abstract Screening**:
    *   **Test Screening**: Screen a sample of the uploaded file (up to 9999 items) with real-time progress updates (SSE) to evaluate criteria and AI performance before full screening.
    *   **Performance Metrics**: After manually assessing the test sample, view detailed performance metrics including Accuracy, Kappa, Confusion Matrix, etc.
    *   **Full Dataset Screening**: Process all abstracts in an RIS file with real-time progress updates (SSE).
*   **Data Extraction (Beta)**:
    *   **User-Defined Fields**: Dynamically define the specific data points (Field Name, Instruction/Question, Example Format) you want to extract from full text.
    *   **Single PDF Processing**: Upload a PDF and instruct the LLM to extract the defined data points.
    *   **JSON Output Focused**: Prompts are designed to encourage JSON output from the LLM.
    *   *(Experimental: Accuracy depends heavily on source document and LLM)*
*   **Result Download**: Download abstract screening results in CSV, Excel, or JSON format.
*   **Parallel Processing**: Utilizes threading for faster screening by making concurrent calls to the LLM API.

## 💻 Technology Stack

*   **Backend**: Python, Flask
*   **Frontend**: HTML, CSS (Bootstrap), JavaScript
*   **LLM Integration**: `requests`, `google-generativeai`, `anthropic`
*   **Data Handling**: `pandas`, `rispy`
*   **PDF Text Extraction**: `PyMuPDF` (fitz)
*   **Metrics**: `scikit-learn`
*   **WSGI Server (Deployment)**: Gunicorn
*   **Deployment Platform**: Render

## 🚀 Getting Started (Local Setup)

Follow these instructions to set up and run the project locally for development or testing.

**Prerequisites:**

*   Python (3.10+ recommended)
*   `pip` (Python package installer)
*   Git

**Setup:**

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd screen_webapp
    ```

2.  **Create and activate a virtual environment:**
    *   On macOS/Linux:
        ```bash
        python3 -m venv .venv
        source .venv/bin/activate
        ```
    *   On Windows:
        ```bash
        python -m venv .venv
        .\.venv\Scripts\activate
        ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables (API Keys):**
    *   Create a file named `.env` in the project root directory (`screen_webapp/`).
    *   Add your API keys to this file, one per line, following the format used by the application (check `config.py` for `api_key_env_var` names). **Do not commit the `.env` file to Git.** Example:
        ```dotenv
        # .env file
        DEEPSEEK_API_KEY=sk-your_deepseek_key_here
        OPENAI_API_KEY=sk-your_openai_key_here
        GEMINI_API_KEY=AIz...your_gemini_key_here
        ANTHROPIC_API_KEY=sk-ant-...your_claude_key_here
        # Optional: Set a fixed secret key for development
        # SECRET_KEY=a_very_strong_random_string_for_flask_session
        ```
    *   *Note: While the application now enforces session-provided keys for screening actions, setting keys in `.env` can be useful for backend testing or as a reference.*

5.  **Run the development server:**
    ```bash
    python app.py
    ```
    The application should be available at `http://127.0.0.1:5050` (or the port specified in `app.py`).

## 📖 Usage Workflow

1.  **LLM Configuration**:
    *   Navigate to the "LLM Configuration" page.
    *   Select the desired LLM Provider and Model.
    *   Enter your API key for the selected provider in the corresponding field. The status and help links are provided.
    *   Click "Save LLM Config". A success message should appear.

2.  **Screening Criteria**:
    *   Navigate to the "Screening Criteria" page.
    *   Use the **Basic Mode** (recommended) or switch to **Advanced Mode**.
    *   Fill in the **Include**, **Exclude**, and **Maybe** conditions for each PICOT element based on your research question. Use the guiding questions and placeholders.
    *   Add any general inclusion/exclusion criteria in the "Other Criteria" sections.
    *   **(Advanced Only)**: Optionally adjust the AI System Prompt and Output Format Instructions. Use caution.
    *   Click "Save Criteria & Settings".

3.  **Abstract Screening**:
    *   Navigate to "Abstract Screening".
    *   **Test**: Upload RIS, set sample size, click "Start Test Screening...". Monitor progress. Click link to view/assess results (`test_results.html`). Calculate metrics.
    *   **Full**: Upload RIS, click "Screen Full File...". Monitor progress. Click link to view results (`results.html`). Download results if needed.

4.  **Data Extraction (Beta)**:
    *   Navigate to "Data Extraction".
    *   Click "+ Add Another Field" to define each data point you want to extract.
        *   **Field Name:** A short key (e.g., `sample_size`).
        *   **Instruction/Question:** Clear question for the AI (e.g., "What was the total sample size?").
        *   **Example Format (Optional):** An example of the desired output (e.g., `150`).
    *   Use the "Tips for Effective Extraction Instructions".
    *   Upload the **single PDF** document you want to extract data from.
    *   Click "Extract Data from PDF". This is a synchronous process; wait for the result page.
    *   Review the extracted data on the results page (`extraction_result.html`). Verify accuracy carefully.

## ⚙️ Configuration

*   **API Keys**: Must be provided via the "LLM Configuration" page for screening actions. Keys are stored in the browser session only. Local development *can* use environment variables defined in a `.env` file (see Setup), but screening actions require session keys.
*   **Screening Criteria**: Configured via the "Screening Criteria" page, including PICOT elements and advanced prompt settings.

## ☁️ Deployment (Render)

This application is configured for deployment on [Render](https://render.com/).

*   It uses `gunicorn` as the WSGI server.
*   The start command used on Render is typically: `gunicorn --workers 4 --bind 0.0.0.0:$PORT app:app`
*   Required environment variables (API keys, `PYTHON_VERSION`, potentially `SECRET_KEY`) must be set in the Render service environment settings.

---

