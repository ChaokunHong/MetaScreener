import os
from kombu import Queue

class Config:
    # Broker and Result Backend Configuration
    broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/1')
    result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
    
    # Task Serialization
    task_serializer = 'json'
    result_serializer = 'json'
    accept_content = ['json']
    
    # Timezone and Time Settings
    timezone = 'UTC'
    enable_utc = True
    
    # Task Routing
    task_routes = {
        'screen_webapp.tasks.process_literature_screening': {'queue': 'literature_screening'},
        'screen_webapp.tasks.process_pdf_screening': {'queue': 'pdf_screening'},
        'screen_webapp.tasks.process_quality_assessment': {'queue': 'quality_assessment'},
        'screen_webapp.tasks.cleanup_temp_files': {'queue': 'maintenance'},
    }
    
    # Queue Configuration
    task_default_queue = 'default'
    task_queues = (
        Queue('default', routing_key='default'),
        Queue('literature_screening', routing_key='literature_screening'),
        Queue('pdf_screening', routing_key='pdf_screening'),
        Queue('quality_assessment', routing_key='quality_assessment'),
        Queue('maintenance', routing_key='maintenance'),
    )
    
    # Worker Configuration
    worker_prefetch_multiplier = 1
    task_acks_late = True
    worker_disable_rate_limits = False
    
    # Task Time Limits (in seconds)
    task_soft_time_limit = 3000  # 50 minutes soft limit
    task_time_limit = 3600       # 60 minutes hard limit
    
    # Task Result Settings
    result_expires = 86400  # Results expire after 24 hours
    
    # Monitoring and Logging
    worker_send_task_events = True
    task_send_sent_event = True
    
    # Performance Settings
    broker_connection_retry_on_startup = True
    broker_connection_retry = True
    broker_connection_max_retries = 5
    
    # Task Retry Settings
    task_retry_jitter = True
    task_default_retry_delay = 60
    task_max_retries = 3
    
    # Security (if needed in production)
    # worker_hijack_root_logger = False
    # worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s' 