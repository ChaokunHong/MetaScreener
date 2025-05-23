from celery import Celery
from celery_config import Config
import os

def make_celery(app_name=None):
    """Create and configure Celery app"""
    celery = Celery(app_name or 'screen_webapp')
    celery.config_from_object(Config)
    
    # Optional: Add task modules
    celery.autodiscover_tasks(['screen_webapp.tasks'])
    
    return celery

# Create Celery instance
celery = make_celery()

# Import tasks to register them
try:
    from screen_webapp import tasks
except ImportError:
    # Tasks will be imported when the module is available
    pass

if __name__ == '__main__':
    celery.start() 