#!/bin/bash

# Screen WebApp Production Startup Script
# For use on Tencent Cloud with 4 GPUs and 16GB RAM

set -e

# Configuration
PROJECT_DIR="/path/to/screen_webapp"  # Update this path
VENV_DIR="$PROJECT_DIR/.venv"
REDIS_CONF="/etc/redis/redis.conf"
LOG_DIR="$PROJECT_DIR/logs"

# Create log directory
mkdir -p "$LOG_DIR"

echo "Starting Screen WebApp Production Environment..."

# Function to check if a service is running
check_service() {
    if pgrep -f "$1" > /dev/null; then
        echo "$1 is already running"
        return 0
    else
        return 1
    fi
}

# Function to start Redis
start_redis() {
    echo "Starting Redis server..."
    if check_service "redis-server"; then
        echo "Redis is already running"
    else
        sudo systemctl start redis-server
        sleep 2
        echo "Redis server started"
    fi
}

# Function to start Celery workers
start_celery() {
    echo "Starting Celery workers..."
    
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    # Start main worker
    if ! check_service "celery.*worker.*default"; then
        celery -A celery_app worker \
            --loglevel=info \
            --queues=default,literature_screening,pdf_screening \
            --concurrency=4 \
            --max-tasks-per-child=1000 \
            --logfile="$LOG_DIR/celery_main.log" \
            --pidfile="$LOG_DIR/celery_main.pid" \
            --detach
        echo "Main Celery worker started"
    fi
    
    # Start quality assessment worker
    if ! check_service "celery.*worker.*quality"; then
        celery -A celery_app worker \
            --loglevel=info \
            --queues=quality_assessment \
            --concurrency=2 \
            --max-tasks-per-child=500 \
            --logfile="$LOG_DIR/celery_quality.log" \
            --pidfile="$LOG_DIR/celery_quality.pid" \
            --detach
        echo "Quality assessment Celery worker started"
    fi
    
    # Start maintenance worker
    if ! check_service "celery.*worker.*maintenance"; then
        celery -A celery_app worker \
            --loglevel=info \
            --queues=maintenance \
            --concurrency=1 \
            --max-tasks-per-child=100 \
            --logfile="$LOG_DIR/celery_maintenance.log" \
            --pidfile="$LOG_DIR/celery_maintenance.pid" \
            --detach
        echo "Maintenance Celery worker started"
    fi
    
    # Start Celery Beat scheduler
    if ! check_service "celery.*beat"; then
        celery -A celery_app beat \
            --loglevel=info \
            --logfile="$LOG_DIR/celery_beat.log" \
            --pidfile="$LOG_DIR/celery_beat.pid" \
            --detach
        echo "Celery Beat scheduler started"
    fi
}

# Function to start Flower monitoring
start_flower() {
    echo "Starting Flower monitoring..."
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    if ! check_service "flower"; then
        celery -A celery_app flower \
            --port=5555 \
            --broker_api=redis://localhost:6379/1 \
            --logfile="$LOG_DIR/flower.log" \
            --pidfile="$LOG_DIR/flower.pid" &
        echo "Flower monitoring started on port 5555"
    fi
}

# Function to start Gunicorn
start_gunicorn() {
    echo "Starting Gunicorn server..."
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    if ! check_service "gunicorn.*app:app"; then
        gunicorn -c gunicorn_config.py app:app \
            --daemon \
            --pid "$LOG_DIR/gunicorn.pid" \
            --access-logfile "$LOG_DIR/gunicorn_access.log" \
            --error-logfile "$LOG_DIR/gunicorn_error.log"
        echo "Gunicorn server started"
    else
        echo "Gunicorn is already running"
    fi
}

# Function to show status
show_status() {
    echo ""
    echo "=== Service Status ==="
    echo "Redis: $(systemctl is-active redis-server)"
    echo "Celery Workers: $(pgrep -f 'celery.*worker' | wc -l) processes"
    echo "Celery Beat: $(pgrep -f 'celery.*beat' | wc -l) processes"
    echo "Flower: $(pgrep -f 'flower' | wc -l) processes"
    echo "Gunicorn: $(pgrep -f 'gunicorn.*app:app' | wc -l) processes"
    echo ""
    echo "=== URLs ==="
    echo "Main App: http://localhost:5000"
    echo "Flower Monitoring: http://localhost:5555"
    echo ""
    echo "=== Log Files ==="
    echo "Logs directory: $LOG_DIR"
    ls -la "$LOG_DIR" 2>/dev/null || echo "No log files yet"
}

# Main execution
case "${1:-start}" in
    start)
        start_redis
        start_celery
        start_flower
        start_gunicorn
        show_status
        ;;
    stop)
        echo "Stopping all services..."
        # Stop Gunicorn
        if [ -f "$LOG_DIR/gunicorn.pid" ]; then
            kill $(cat "$LOG_DIR/gunicorn.pid") 2>/dev/null || true
            rm -f "$LOG_DIR/gunicorn.pid"
        fi
        
        # Stop Celery
        pkill -f "celery.*worker" || true
        pkill -f "celery.*beat" || true
        pkill -f "flower" || true
        
        # Clean up PID files
        rm -f "$LOG_DIR"/*.pid
        
        echo "All services stopped"
        ;;
    restart)
        $0 stop
        sleep 3
        $0 start
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac 