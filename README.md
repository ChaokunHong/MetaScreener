# MetaScreener: AI-Assisted Literature Screening

MetaScreener is a web application designed to streamline the literature screening process for systematic reviews, particularly in the medical field, using Large Language Models (LLMs). It helps researchers efficiently filter large volumes of abstracts based on predefined inclusion and exclusion criteria.

**Live Application:** [https://metascreener.onrender.com](https://metascreener.onrender.com)

## ✨ Features

*   **RIS File Upload**: Supports uploading citation library files in `.ris` format.
*   **Configurable LLM**: Choose from major LLM providers and models:
    *   DeepSeek (Chat, Reasoner)
    *   OpenAI (GPT-3.5 Turbo, GPT-4, GPT-4 Turbo, GPT-4o)
    *   Google Gemini (1.0 Pro, 1.5 Pro, 1.5 Flash)
    *   Anthropic Claude (Haiku, Sonnet, Opus, 2.1)
*   **Secure API Key Handling**: Requires user-provided API keys stored *only* in the browser session for the duration of the visit (not recorded server-side). Links provided for obtaining keys.
*   **Structured Screening Criteria**: Define detailed criteria using the PICOT framework, with specific fields for **Include**, **Exclude**, and **Maybe** conditions for each element (Population, Intervention, Comparison, Outcome, Time/Type).
*   **AI Prompt Customization (Advanced)**: Advanced users can modify the underlying System Prompt and Output Format Instructions sent to the LLM.
*   **Guided Input**: Hints and placeholders guide users in formulating effective criteria.
*   **Test Screening**: Screen a sample of the uploaded file (up to 9999 items) with real-time progress updates (SSE) to evaluate criteria and AI performance before full screening.
*   **Performance Metrics**: After manually assessing the test sample, view detailed performance metrics including:
    *   Overall Accuracy, Cohen's Kappa, Discrepancy Rate
    *   3x3 Confusion Matrix (Include/Exclude/Maybe) with color highlighting
    *   Per-Class Precision, Recall, F1, Specificity
    *   Binary task metrics (Sensitivity, Precision, F1, Specificity for Include vs. Not Include)
    *   Workload Reduction (%)
    *   Maybe Rate Analysis
*   **Full Dataset Screening**: Process the entire RIS file with real-time progress updates (SSE).
*   **Parallel Processing**: Utilizes threading for faster screening by making concurrent calls to the LLM API.

## 💻 Technology Stack

*   **Backend**: Python, Flask
*   **Frontend**: HTML, CSS (Bootstrap), JavaScript
*   **LLM Integration**: `requests`, `google-generativeai`, `anthropic`
*   **Data Handling**: `pandas`, `rispy`
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

3.  **Screening Actions**:
    *   Navigate to the "Screening Actions" page.
    *   **Test Screening**:
        *   Upload your `.ris` file.
        *   Set the desired sample size (5-9999).
        *   Click "Start Test Screening with Progress".
        *   Monitor the progress bar and log.
        *   Once complete, click the "View Test Results & Assess" link.
    *   **Assess Test Results (on `test_results.html`)**:
        *   Review the AI's decision and reasoning for each sample item.
        *   Provide your own assessment (Include/Exclude/Maybe) using the radio buttons for each item.
        *   Click "Calculate Metrics & Compare".
    *   **View Metrics (on `metrics_results.html`)**:
        *   Analyze the performance metrics and confusion matrix.
        *   Review the individual item comparison.
        *   Optionally, click "Screen Full Dataset (from Test)" to start processing the entire file using the same settings (requires API key in session).
    *   **Full Dataset Screening**:
        *   Upload your `.ris` file.
        *   Click "Screen Full File with Progress (SSE)".
        *   Monitor the progress bar and log.
        *   Once complete, click the "View Full Results from SSE Screening" link to see the results on the `results.html` page.

## ⚙️ Configuration

*   **API Keys**: Must be provided via the "LLM Configuration" page for screening actions. Keys are stored in the browser session only. Local development *can* use environment variables defined in a `.env` file (see Setup), but screening actions require session keys.
*   **Screening Criteria**: Configured via the "Screening Criteria" page, including PICOT elements and advanced prompt settings.

## ☁️ Deployment (Render)

This application is configured for deployment on [Render](https://render.com/).

*   It uses `gunicorn` as the WSGI server.
*   The start command used on Render is typically: `gunicorn --workers 4 --bind 0.0.0.0:$PORT app:app`
*   Required environment variables (API keys, `PYTHON_VERSION`, potentially `SECRET_KEY`) must be set in the Render service environment settings.

---

