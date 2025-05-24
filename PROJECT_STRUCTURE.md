# Project Structure

## Overview
This project has been reorganized for better modularity and maintainability.

## Directory Structure

```
screen_webapp/
├── app/                        # Main application package
│   ├── __init__.py
│   ├── core/                   # Core application components
│   │   ├── __init__.py
│   │   └── app.py             # Main Flask application
│   ├── celery_tasks/          # Asynchronous task processing
│   │   ├── __init__.py
│   │   ├── celery_app.py      # Celery configuration
│   │   └── tasks.py           # Task definitions
│   ├── quality_assessment_module/  # Quality assessment feature
│   │   ├── __init__.py
│   │   ├── routes.py          # Blueprint routes
│   │   ├── services.py        # Business logic
│   │   ├── redis_storage.py   # Redis integration
│   │   ├── models/            # ML models
│   │   ├── prompts/           # LLM prompts
│   │   ├── templates/         # HTML templates
│   │   └── data/              # Data storage
│   ├── screening/             # Screening functionality (future)
│   ├── static/                # Static assets
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   ├── templates/             # HTML templates
│   └── utils/                 # Utility functions
│       ├── __init__.py
│       ├── utils.py           # General utilities
│       └── rate_limiter.py    # Rate limiting
├── config/                    # Configuration files
│   ├── __init__.py
│   ├── config.py              # Main configuration
│   └── celery_config.py       # Celery configuration
├── deployment/                # Deployment scripts
│   ├── gunicorn_config.py     # Gunicorn configuration
│   ├── start_production.sh    # Production startup script
│   └── Procfile               # Process definition
├── scripts/                   # Utility scripts
├── logs/                      # Application logs
├── uploads/                   # File uploads
├── run.py                     # Development server entry point
├── wsgi.py                    # WSGI entry point for production
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation
└── .gitignore                 # Git ignore rules
```

## Key Changes

1. **Modular Structure**: The application is now organized into logical modules.
2. **Clear Separation**: Configuration, deployment, and application code are separated.
3. **Import Paths**: All imports have been updated to reflect the new structure.
4. **Entry Points**: 
   - `run.py` for development
   - `wsgi.py` for production deployment

## Running the Application

### Development
```bash
python run.py
```

### Production
```bash
cd deployment
./start_production.sh start
```

## Import Examples

```python
# From anywhere in the project:
from app.core.app import app
from app.utils.utils import load_literature_ris
from config.config import get_llm_providers_info
from app.celery_tasks.tasks import process_literature_screening
``` 