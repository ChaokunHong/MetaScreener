# MetaScreener: AI-Assisted Literature Screening Tool

<div align="center">
<img src="static/images/logo_optimized.png" alt="MetaScreener Logo" width="300"/>

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0%2B-green.svg)](https://flask.palletsprojects.com/)
[![LLM Integration](https://img.shields.io/badge/LLM-Multi--Provider-purple.svg)](https://github.com/ChaokunHong/MetaScreener)

**Fast, accurate AI-assisted literature screening tool for systematic reviews and meta-analyses**

**Live Application:** [https://www.metascreener.net/](https://www.metascreener.net/) (Tencent Cloud - Primary)  
**Alternative Deployment:** [https://metascreener.onrender.com](https://metascreener.onrender.com) (Render.com)
</div>

## 📖 Table of Contents

- [System Overview](#-system-overview)
- [Core Features](#-core-features)
- [Technical Architecture](#-technical-architecture)
- [Detailed Functionality](#-detailed-functionality)
  - [User Interface](#user-interface)
  - [LLM Configuration](#llm-configuration) 
  - [Screening Criteria Frameworks](#screening-criteria-frameworks)
  - [Abstract Screening](#abstract-screening)
  - [Full-text Screening](#full-text-screening)
  - [Data Extraction](#data-extraction)
  - [Batch Processing](#batch-processing)
- [Installation Guide](#-installation-guide)
  - [Environment Requirements](#environment-requirements)
  - [Dependency Installation](#dependency-installation)
  - [Configuration Options](#configuration-options)
- [Usage Guide](#-usage-guide)
  - [Workflow](#workflow)
  - [Best Practices](#best-practices)
- [Deployment Options](#-deployment-options)
  - [Local Development Environment](#local-development-environment)
  - [Production Environment](#production-environment)
  - [Cloud Services](#cloud-services)
- [System Architecture](#-system-architecture)
  - [Code Organization](#code-organization)
  - [Data Flow](#data-flow)
- [Security and Privacy](#-security-and-privacy)
- [Performance Optimization](#-performance-optimization)
- [Frequently Asked Questions](#-frequently-asked-questions)
- [Contribution Guidelines](#-contribution-guidelines)
- [Changelog](#-changelog)
- [Development Roadmap](#-development-roadmap)
- [Author Information](#-author-information)
- [Disclaimer](#-disclaimer)

## 🔍 System Overview

MetaScreener is a web application specifically designed for medical literature screening, utilizing Large Language Model (LLM) technology to significantly enhance the efficiency and accuracy of systematic literature reviews. The system supports screening large volumes of abstracts from RIS files and processing full-text PDF documents based on user-defined inclusion/exclusion criteria. MetaScreener integrates multiple advanced LLM provider interfaces, emphasizes secure session-based API key handling, and provides researchers with a one-stop solution for literature screening.

**Primary Use Cases**:
- Literature screening for systematic reviews and meta-analyses
- Evidence-based medical research
- Initial screening of large literature databases
- Collaborative screening by research teams

**Key Benefits**:
- Reduces literature screening time by over 80%
- Improves consistency and accuracy of the screening process
- Decreases cognitive burden on researchers
- Standardizes screening workflows and decision rationales

## ✨ Core Features

### Flexible Input Formats
- **RIS File Processing**: Supports standard research literature database export formats for efficient batch abstract screening
- **PDF Full-text Processing**: Supports single file and batch PDF upload and processing for detailed literature evaluation
- **Intelligent Text Extraction**: Combines PyMuPDF direct extraction with Tesseract OCR technology to ensure comprehensive text retrieval
- **Metadata Management**: Automatically extracts PDF metadata to enhance document organization and citation

### Diverse LLM Provider Integration
- **Comprehensive Provider Support**: 
  - DeepSeek
  - OpenAI (ChatGPT)
  - Google (Gemini)
  - Anthropic (Claude)
- **Model Selection Flexibility**: Each provider supports multiple models to meet different precision and speed requirements
- **Secure API Key Management**: Keys are stored only in browser sessions, ensuring security

### Advanced Screening Criteria Frameworks
- **Multiple Standardized Frameworks**:
  - PICOT (Population, Intervention, Comparison, Outcome, Time)
  - SPIDER (Sample, Phenomenon, Intervention, Data, Evaluation, Research)
  - PICOS (Population, Intervention, Comparison, Outcome, Study Design)
  - PECO (Population, Exposure, Comparison, Outcome)
  - PICOC (Population, Intervention, Comparison, Outcome, Context)
  - ECLIPSE (Expectation, Client group, Location, Impact, Professionals, SErvice)
  - CLIP (Client, Location, Intervention, Professionals)
  - BeHEMoTh (Behaviour of interest, Health context, Exclusions, Models or Theories)
- **Fine-grained Decision Conditions**: Each framework element supports Include, Exclude, and Maybe conditions
- **Custom Prompts**: Advanced users can customize AI system prompts and output formats

### Comprehensive Screening Workflow
- **Abstract Screening**
  - Keyword filtering
  - Line number range filtering
  - Test screening with performance evaluation
  - Full dataset real-time processing
- **Full-text PDF Screening**
  - Single file detailed analysis
  - Batch PDF parallel processing
  - Page preview and extracted text view
- **Data Extraction**
  - Custom extraction field definition with user-specified names and descriptions
  - Template-based extraction instruction settings for structured data capture
  - JSON schema configuration for consistent output formatting
  - Support for multiple data fields with complex relationships

### User Experience Enhancements
- **Professional Landing Page**: Clear and concise entry guidance
- **Real-time Progress Feedback**: SSE (Server-Sent Events) based processing progress display
- **Result Visualization**: Includes performance metrics, confusion matrices, and statistical summaries
- **Batch Processing Optimization**: Upload file preview, filtering, and removal options
- **Result Export**: Supports CSV, Excel, and JSON format export of screening results

## 🚀 Technical Architecture

### Backend Stack
- **Core Framework**: Python + Flask
- **WSGI Server**: Gunicorn
- **LLM Integration**: Provider-specific Python SDKs
- **Data Processing**:
  - pandas (dataframe processing)
  - rispy (RIS file parsing)
  - PyMuPDF (PDF text extraction)
  - Pytesseract (OCR functionality)
- **Task Scheduling**: APScheduler
- **Performance Optimization**: ThreadPoolExecutor concurrent processing
- **Metrics Calculation**: scikit-learn

### Frontend Stack
- **Markup Language**: HTML5
- **Styling**: CSS3 (Bootstrap 4)
- **Client-side Scripting**: JavaScript
- **PDF Rendering**: pdf.js
- **Real-time Feedback**: Server-Sent Events (SSE)

### Deployment and Configuration
- **Deployment Platforms**:
  - Tencent Cloud (primary deployment)
  - Render.com (alternative deployment)
- **Configuration Management**: python-dotenv
- **Reverse Proxy**: Nginx (production environment)

## 📊 Detailed Functionality

### User Interface
- **Basic Layout**:
  - Responsive design, adapting to different devices
  - Consistent navigation bar and footer
  - Unified theme colors for interface elements
- **Homepage Design**:
  - Feature overview area
  - Quick start guide
  - Main functionality entry points
- **Activity Status Indication**:
  - Current page highlighting
  - Loading indicators for processing operations
  - Visual feedback for success/failure states

### LLM Configuration
- **Provider Management**:
  - Dynamic loading of supported provider list
  - Provider API documentation links
  - Visual indication of currently selected provider
- **Model Selection**:
  - Provider-filtered model list
  - Model capability descriptions
  - Default recommended model indicators
- **API Key Handling**:
  - Session-level key storage
  - Key status display (Not set/Using environment default/Set in session)
  - Key clearing options
  - Key show/hide toggle

### Screening Criteria Frameworks
- **Framework Selection**:
  - Eight standardized framework dropdown options
  - Framework introduction and applicable scenarios
  - Data retention options when switching frameworks
- **Criteria Definition Interface**:
  - Sectioned paragraph layout
  - Input areas for each element's include/exclude/maybe conditions
  - Example text and tips
  - Formatted preview
- **Advanced Settings**:
  - System prompt customization
  - Output format instruction customization
  - Default value reset options

### Abstract Screening
- **File Processing**:
  - RIS file validation and upload
  - File parsing progress feedback
  - Abstract extraction and formatting
- **Screening Filters**:
  - Title keyword filtering
  - Line number range limitation
  - Clear filter options
- **Test Screening**:
  - Sample size settings
  - Random sampling methods
  - Real-time processing progress display
- **Performance Evaluation**:
  - Confusion matrix visualization
  - Cohen's Kappa coefficient calculation
  - Precision, recall, F1 score and other metrics
  - Workload reduction rate estimation
- **Full Dataset Screening**:
  - Parallel processing optimization
  - Real-time progress updates
  - Paginated result display
  - Expandable/collapsible detail views

### Full-text Screening
- **Single File Screening**:
  - PDF file upload and validation
  - Text extraction processing
  - OCR fallback processing
  - Page number and line number marking
- **Document Preview**:
  - Original PDF interactive preview
  - Extracted text page display
  - Page navigation controls
- **Batch Processing**:
  - Multiple file selection and upload
  - Upload queue preview
  - Filename filtering
  - Upload order filtering
- **Result Management**:
  - Batch processing statistical summary
  - Result sorting options
  - Multiple format exports
  - Result caching and recovery

### Data Extraction
- **Extraction Configuration**:
  - Custom field definition with user-specified names and descriptions
  - Template-based extraction instruction settings for structured data capture
  - JSON schema configuration for consistent output formatting
  - Support for multiple data fields with complex relationships
- **Processing Control**:
  - Real-time extraction progress monitoring with status indicators
  - Robust error handling with detailed diagnostics and recovery options
  - Interactive result preview with expandable/collapsible fields
  - Content validation against defined schema rules
- **Data Output**:
  - Structured JSON output with nested field relationships
  - Tabularized data view for easy readability
  - Multiple export options (JSON, CSV, Excel)
  - Citation metadata preservation
  - Extracted data can be directly integrated with analysis workflows

### Batch Processing
- **Queue Management**:
  - Processing priority settings
  - Queue status monitoring
  - Failed task retry
- **Resource Optimization**:
  - Dynamic thread pool adjustment
  - Memory usage monitoring
  - Timeout handling
- **Result Aggregation**:
  - Batch processing statistical reports
  - Anomaly situation flagging
  - Result set exports

## 💻 Installation Guide

### Environment Requirements
- **Operating System**:
  - Linux, macOS, or Windows
  - Ubuntu 20.04+ recommended for server deployment
- **Python Version**: 3.10+ (3.11 recommended)
- **Hardware Requirements**:
  - Memory: 2GB minimum, 4GB+ recommended
  - Storage: At least 1GB available space
  - CPU: Multi-core processor (parallel processing optimization)
- **Network**: Stable internet connection (for external LLM API calls)
- **External Dependencies**:
  - Tesseract OCR engine (for PDF OCR functionality)
  - (Optional) Nginx (for production deployment)

### Dependency Installation
#### Basic Setup
```bash
# Clone repository
git clone https://github.com/ChaokunHong/MetaScreener.git
cd MetaScreener

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or .\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

#### Tesseract OCR Installation
**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-eng
# Optional: Install additional language packs
# sudo apt-get install tesseract-ocr-chi-sim
```

**macOS (using Homebrew)**:
```bash
brew install tesseract tesseract-lang
```

**Windows**:
Download installer from the [Tesseract GitHub page](https://github.com/UB-Mannheim/tesseract/wiki).

### Configuration Options
Create an `.env` file in the project root directory:
```dotenv
# --- LLM API Keys (Optional - can also be set through UI session) ---
# DEEPSEEK_API_KEY=sk-your_deepseek_key_here
# OPENAI_API_KEY=sk-your_openai_key_here
# GEMINI_API_KEY=AIz...your_gemini_key_here
# ANTHROPIC_API_KEY=sk-ant-...your_claude_key_here

# --- Flask Configuration (Optional but recommended) ---
# SECRET_KEY=strong_random_string_for_session_security
# FLASK_DEBUG=1  # Set in development mode

# --- Tesseract OCR Configuration (Optional) ---
# TESSERACT_CMD_PATH=/usr/bin/tesseract  # Set Tesseract path if not in system PATH
# PDF_OCR_THRESHOLD_CHARS=50  # Minimum character threshold to skip OCR

# --- Log Level (Optional) ---
# LOGLEVEL=DEBUG  # More detailed logs (default is INFO)
```

## 📘 Usage Guide

### Workflow
The standard workflow for MetaScreener includes the following steps:

#### 1. Initial Configuration
- Visit the homepage to understand system overview
- Navigate to "Configure LLM & Start" or directly to "View Screening Actions"

#### 2. LLM Configuration (`/llm_config`)
- Select LLM provider and model
- Enter API key (will be stored in current browser session)
- Confirm key status (Not set/Using environment default/Set)
- Save configuration

#### 3. Screening Criteria Setup (`/criteria`)
- Select appropriate criteria framework for your research (PICOT, SPIDER, etc.)
- Define Include, Exclude, and Maybe conditions for each framework element
- Optionally use advanced mode to customize AI prompts and output format
- Save criteria or reset to default examples as needed

#### 4. Screening Action Selection (`/screening_actions`)
- Interface provides links to different screening modules

#### 5. Abstract Screening (`/abstract_screening`)
- Upload .ris file
- Optionally filter literature by title keywords or line number range
- Perform test screening (on a sample), view detailed performance metrics
- Perform full dataset screening, view results and download

#### 6. Full-text PDF Screening (`/full_text_screening`)
- **Single PDF Mode**: Upload, screen, view results (including extracted text and PDF preview)
- **Batch PDF Mode**: Upload multiple PDFs, filter/remove selected files, filter by filename or upload order, process in parallel, view and download batch results

#### 7. Data Extraction (Beta) (`/data_extraction`)
- Define custom data fields to extract from a single PDF

### Best Practices
- **Framework Selection**: Choose appropriate screening framework based on research type:
  - PICOT: Suitable for intervention studies
  - PICOS: Suitable for systematic reviews
  - PECO: Suitable for epidemiological studies
  - SPIDER: Suitable for qualitative research
- **Test Screening**: Always run test screening on a sample first to validate AI decision quality
- **Criteria Adjustment**: Adjust screening criteria based on test results to improve accuracy
- **Incremental Processing**: Consider dividing files into smaller groups when processing large batches
- **Result Verification**: Manually review automated decisions, especially "MAYBE" decisions
- **API Key Management**: Use temporarily stored session keys, avoid saving keys in environment variables
- **Regular Backups**: Regularly export screening results to prevent session expiration loss

## 🌐 Deployment Options

### Local Development Environment
```bash
# Ensure virtual environment is activated
# source venv/bin/activate or .\venv\Scripts\activate

# Use Flask's built-in server (good for development)
export FLASK_APP=app.py
export FLASK_DEBUG=1  # Optional, enables debug mode
flask run --host=0.0.0.0 --port=5050

# Or run directly (if app.py contains app.run() code)
python app.py
```

### Production Environment

#### Gunicorn Setup
```bash
# Ensure Gunicorn is installed
pip install gunicorn

# Run Gunicorn with appropriate configuration
gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
```

#### Nginx Configuration (Example)
```nginx
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Support for SSE
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        
        # Important: Allow large file uploads
        client_max_body_size 100M;
    }
}
```

#### Systemd Service (Example)
```ini
# /etc/systemd/system/metascreener.service
[Unit]
Description=MetaScreener Gunicorn Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/MetaScreener
ExecStart=/path/to/MetaScreener/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

### Cloud Services

#### Tencent Cloud Deployment (Primary Deployment)
- Use Tencent Cloud ECS instance
- Configure Nginx as reverse proxy
- Set up SSL certificate
- Configure firewall rules (allow ports 80/443)
- Configure application to run automatically via Systemd service

#### Render.com Deployment (Alternative Deployment)
- Create new Web Service on Render.com
- Set build command: `pip install -r requirements.txt`
- Set start command: `gunicorn --workers 4 --bind 0.0.0.0:$PORT app:app`
- Configure necessary environment variables
- Deploy application

## 🔧 System Architecture

### Code Organization
```
MetaScreener/
├── app.py                 # Main application entry point
├── config.py              # Configuration definitions and utility functions
├── utils.py               # Common utility function set
├── requirements.txt       # Dependency library list
├── README.md              # Project documentation
├── Procfile               # Render.com deployment configuration
├── .env                   # Environment variable configuration (local development)
├── static/                # Static resource directory
│   └── images/            # Image resources
│       └── logo.png       # Application logo
├── templates/             # HTML template directory
│   ├── base.html          # Base template (contains common layout)
│   ├── index.html         # Homepage template
│   ├── llm_configuration.html # LLM configuration page
│   ├── screening_criteria.html # Screening criteria configuration page
│   ├── screening_actions.html  # Screening action selection page
│   ├── abstract_screening.html # Abstract screening page
│   ├── full_text_screening.html # Full-text screening page
│   ├── results.html       # Screening results page
│   ├── test_results.html  # Test screening results page
│   ├── metrics_results.html # Performance metrics results page
│   ├── pdf_result.html    # PDF screening results page
│   ├── batch_pdf_results.html # Batch PDF screening results page
│   ├── data_extraction.html # Data extraction page
│   └── extraction_result.html # Data extraction results page
└── uploads/               # Uploaded file temporary storage directory
```

### Data Flow
1. **Input Processing**:
   - RIS files parsed into pandas DataFrame via `rispy`
   - PDF files have text extracted via `PyMuPDF`+`Tesseract OCR`
   - User criteria submitted via web forms, stored in session

2. **AI Processing**:
   - Build prompt = system prompt + screening criteria + text content + output format requirements
   - Submit prompt through selected LLM's API
   - Parse API response, extract decision label and explanation

3. **Parallel Processing**:
   - Batch tasks use `ThreadPoolExecutor` to create thread pool
   - Tasks assigned to threads, asynchronously execute API calls
   - Results streamed to frontend via SSE

4. **Result Management**:
   - Temporary results stored in application memory (dictionaries/cache)
   - PDF file results use `TTLCache` (2-hour expiration)
   - Long-term cached data periodically cleaned via background tasks

5. **File Cleanup**:
   - Batch processing PDFs deleted immediately after processing
   - Single-file preview PDFs periodically cleaned via `APScheduler` tasks
   - Session data cleared when browser session ends

## 🔒 Security and Privacy

- **API Key Handling**:
  - Keys stored only in current browser session
  - Automatically cleared after session ends
  - Not persistently stored on server backend
  - Transmitted via HTTPS to prevent man-in-the-middle attacks

- **File Handling**:
  - Uploaded files temporarily stored on server
  - Batch processing PDFs deleted immediately after processing
  - Single file PDFs retained for a few hours at most before deletion
  - Filenames use UUID prefixes to prevent conflicts

- **Session Security**:
  - Uses Flask's secure session mechanism
  - Session key configured via environment variable
  - Prevention of session fixation attacks
  - Regular session rotation

- **Input Validation**:
  - File type validation
  - File size limitations
  - Filename security handling
  - Content type validation

- **CORS Policy**:
  - Cross-origin request limitations based on deployment environment
  - Appropriate content security policy settings
  - Prevention of unauthorized API calls

## ⚡ Performance Optimization

- **Concurrent Processing**:
  - ThreadPoolExecutor manages parallel API calls
  - Batch tasks automatically load balanced
  - Dynamic thread count adjustment based on server load

- **Caching Strategy**:
  - TTLCache for PDF processing results
  - LLM configuration and screening criteria cached in session
  - Avoids reprocessing identical content

- **Chunked Processing**:
  - Large RIS files processed in batches
  - Large PDFs use paging strategy
  - Stream transmission for long processing task results

- **Resource Management**:
  - Timely cleanup of temporary files to free disk space
  - Memory usage monitoring and optimization
  - Regular garbage collection of expired cache data

- **Background Task Scheduling**:
  - APScheduler manages periodic maintenance tasks
  - Non-critical operations executed asynchronously
  - Smooth handling of load peaks

## ❓ Frequently Asked Questions

1. **API Key Configuration Issues**
   - **Problem**: API key not saved or invalid
   - **Solution**: Confirm API key is correct and properly saved in session; check account balance is sufficient

2. **File Processing Errors**
   - **Problem**: RIS file parsing failure
   - **Solution**: Ensure RIS file uses correct encoding format (UTF-8); verify file structure conforms to standards

3. **PDF Text Extraction Issues**
   - **Problem**: Incomplete PDF text extraction results
   - **Solution**: Confirm PDF is not scanned or image-based; check Tesseract OCR installation is correct

4. **LLM Response Parsing Errors**
   - **Problem**: LLM returned content cannot be correctly parsed into decision labels
   - **Solution**: Adjust output format instructions; check LLM response completeness

5. **Batch Processing Performance Issues**
   - **Problem**: Batch processing becomes slow or times out
   - **Solution**: Reduce batch processing scale; adjust thread count; check network connection stability

6. **File Upload Failures**
   - **Problem**: Large PDF upload fails (413 error)
   - **Solution**: Check `client_max_body_size` parameter in Nginx configuration; adjust Flask upload limits

7. **Session Expiration Issues**
   - **Problem**: Results lost after screening interruption
   - **Solution**: Periodically save partial results; reduce batch processing scale

8. **Deployment Issues**
   - **Problem**: Gunicorn startup failure
   - **Solution**: Check dependency installation completeness; verify permission configuration; check logs for detailed error information

## 📈 Changelog

### v1.0.0 (2025-05-13)
- Initial version release


## 🚀 Development Roadmap

### Near-term Plans
- **User Account System**: Implement user registration, login, and personal settings
- **Project Management**: Support saving and organizing multiple screening projects
- **Team Collaboration**: Add multi-user collaboration and role management
- **Advanced Data Analysis**: Integrate richer result analysis and visualization

### Mid-term Goals
- **Annotations and Comments**: Support annotations, discussions, and revisions of results
- **API Interface**: Provide programmatic access interface
- **Offline Mode**: Support offline use of some functionality

### Long-term Vision
- **Adaptive Learning**: Optimize screening decisions based on user feedback
- **Integration Extensions**: Deep integration with literature management software and academic databases
- **Mobile Application**: Develop companion mobile application
- **Multilingual Support**: Extend UI and processing capabilities to multiple languages

## 👥 Author Information

MetaScreener was developed by the following researchers:

**Chaokun Hong**
- chaokun.hong@ndm.ox.ac.uk
- Centre for Tropical Medicine and Global Health, Nuffield Department of Medicine, University of Oxford

**Thao Phuong Nguyen**
- ngthao.20107@gmail.com
- Oxford University Clinical Research Unit, National Hospital for Tropical Diseases, Hanoi, Vietnam

We welcome feedback about MetaScreener's performance, functionality, and improvements, especially usage data from actual literature screening workflows (sensitivity, specificity, time saved, etc.). Your real-world usage data is invaluable for improving this tool!

## ⚖️ Disclaimer

MetaScreener is provided "as-is" without any warranties of any kind, express or implied. The accuracy of AI-driven screening and data extraction heavily depends on the chosen LLM, the quality of the input data, and the clarity of the defined criteria. Users are solely responsible for verifying all results and making final decisions. The developers assume no liability for any outcomes resulting from the use of this software. Please use responsibly and in accordance with all applicable ethical guidelines and institutional policies.

---

<div align="center">
© 2025 Chaokun Hong & Thao Phuong Nguyen | Nuffield Department of Medicine, University of Oxford & Oxford University Clinical Research Unit
</div>

