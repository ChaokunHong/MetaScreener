import multiprocessing
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gevent"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Worker timeouts
timeout = 3600  # 60 minutes for long-running tasks
keepalive = 5
graceful_timeout = 30

# Memory management
preload_app = True
max_worker_memory = 2048  # MB - restart worker if it uses more than 2GB
worker_tmp_dir = "/dev/shm" if os.path.exists("/dev/shm") else None

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "screen_webapp"

# SSL (if needed in production)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Security
limit_request_line = 8192
limit_request_fields = 100
limit_request_field_size = 8190

# Environment variables - All Redis configurations use consistent databases
raw_env = [
    "CELERY_BROKER_URL=redis://localhost:6379/1",
    "CELERY_RESULT_BACKEND=redis://localhost:6379/2", 
    "REDIS_URL=redis://localhost:6379/1",  # Fixed: Use same database as CELERY_BROKER_URL
    "FLASK_ENV=production",
    "FLASK_APP=app.py",
]

# Hooks
def pre_fork(server, worker):
    """Called just before a worker is forked"""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked"""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT"""
    worker.log.info("Worker received INT or QUIT signal")

def when_ready(server):
    """Called just after the server is started"""
    server.log.info("Server is ready. Spawning workers")

def on_exit(server):
    """Called just before exiting"""
    server.log.info("Shutting down: Master")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP"""
    server.log.info("Reloading workers")

# Application import
# 'app' should point to the application object in your app module
# Update the path to match new structure
from app.core.app import app 