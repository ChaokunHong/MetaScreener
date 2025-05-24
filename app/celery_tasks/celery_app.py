from celery import Celery
import os
import sys

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.celery_config import Config

def make_celery(app_name=None):
    """Create and configure Celery app"""
    celery = Celery(app_name or 'screen_webapp')
    celery.config_from_object(Config)
    
    # Optional: Add task modules
    celery.autodiscover_tasks(['app.celery_tasks'])
    
    return celery

# Create Celery instance
celery = make_celery()
# Add app alias to support different import patterns
app = celery

# Import tasks to register them
try:
    from app.celery_tasks import tasks
    print("Tasks imported and registered successfully")
except ImportError as e:
    print(f"Failed to import tasks: {e}")
    # Tasks will be imported when the module is available
    pass

if __name__ == '__main__':
    celery.start() 