"""
Redis storage utilities for quality assessment batch data
Provides persistent storage for batch assessment status to survive server restarts
"""

import json
import redis
import os
from typing import Dict, Optional, Any
from flask import current_app

# Redis connection for batch storage
_redis_client = None

def get_redis_client():
    """Get Redis client for batch storage"""
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client

def save_batch_status(batch_id: str, batch_data: Dict[str, Any]) -> bool:
    """Save batch assessment status to Redis"""
    try:
        redis_client = get_redis_client()
        key = f"qa_batch:{batch_id}"
        # Set expiration to 7 days (604800 seconds)
        redis_client.setex(key, 604800, json.dumps(batch_data))
        current_app.logger.info(f"REDIS_STORAGE: Saved batch {batch_id} to Redis")
        return True
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE: Error saving batch {batch_id}: {e}")
        return False

def get_batch_status(batch_id: str) -> Optional[Dict[str, Any]]:
    """Get batch assessment status from Redis"""
    try:
        redis_client = get_redis_client()
        key = f"qa_batch:{batch_id}"
        data = redis_client.get(key)
        if data:
            batch_data = json.loads(data)
            current_app.logger.info(f"REDIS_STORAGE: Retrieved batch {batch_id} from Redis")
            return batch_data
        else:
            current_app.logger.warning(f"REDIS_STORAGE: Batch {batch_id} not found in Redis")
            return None
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE: Error retrieving batch {batch_id}: {e}")
        return None

def update_batch_status(batch_id: str, updates: Dict[str, Any]) -> bool:
    """Update specific fields in batch status"""
    try:
        batch_data = get_batch_status(batch_id)
        if batch_data:
            batch_data.update(updates)
            return save_batch_status(batch_id, batch_data)
        else:
            current_app.logger.warning(f"REDIS_STORAGE: Cannot update non-existent batch {batch_id}")
            return False
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE: Error updating batch {batch_id}: {e}")
        return False

def delete_batch_status(batch_id: str) -> bool:
    """Delete batch assessment status from Redis"""
    try:
        redis_client = get_redis_client()
        key = f"qa_batch:{batch_id}"
        result = redis_client.delete(key)
        current_app.logger.info(f"REDIS_STORAGE: Deleted batch {batch_id} from Redis")
        return bool(result)
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE: Error deleting batch {batch_id}: {e}")
        return False

def list_all_batches() -> Dict[str, Dict[str, Any]]:
    """List all batch assessment statuses (for debugging)"""
    try:
        redis_client = get_redis_client()
        keys = redis_client.keys("qa_batch:*")
        batches = {}
        for key in keys:
            batch_id = key.replace("qa_batch:", "")
            data = redis_client.get(key)
            if data:
                batches[batch_id] = json.loads(data)
        current_app.logger.info(f"REDIS_STORAGE: Found {len(batches)} batches in Redis")
        return batches
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE: Error listing batches: {e}")
        return {} 