"""
Redis storage utilities for quality assessment batch data
Provides persistent storage for batch assessment status to survive server restarts
"""

import json
import redis
import os
from typing import Dict, Optional, Any, List
from flask import current_app

# Redis connection for batch storage
_redis_client = None

def get_redis_client():
    """Get Redis client for batch storage"""
    global _redis_client
    if _redis_client is None:
        # Use the same Redis database as Celery broker (db=1) for consistency
        redis_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        print(f"REDIS_BATCH_STORAGE: Using Redis URL {redis_url}")
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

def save_batch_status_pipeline(batch_id: str, batch_data: Dict[str, Any], pipe=None) -> bool:
    """Save batch assessment status to Redis using pipeline for better performance"""
    try:
        redis_client = get_redis_client()
        
        if pipe is None:
            pipe = redis_client.pipeline()
            execute_pipe = True
        else:
            execute_pipe = False
            
        key = f"qa_batch:{batch_id}"
        # Set expiration to 7 days (604800 seconds)
        pipe.setex(key, 604800, json.dumps(batch_data))
        
        if execute_pipe:
            pipe.execute()
            
        current_app.logger.info(f"REDIS_STORAGE_PIPELINE: Queued batch {batch_id} for Redis save")
        return True
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE_PIPELINE: Error saving batch {batch_id}: {e}")
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

def get_multiple_batch_status(batch_ids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Get multiple batch assessment statuses from Redis using pipeline"""
    try:
        redis_client = get_redis_client()
        pipe = redis_client.pipeline()
        
        keys = [f"qa_batch:{batch_id}" for batch_id in batch_ids]
        for key in keys:
            pipe.get(key)
            
        results = pipe.execute()
        
        batch_data = {}
        for i, batch_id in enumerate(batch_ids):
            if results[i]:
                try:
                    batch_data[batch_id] = json.loads(results[i])
                except json.JSONDecodeError:
                    batch_data[batch_id] = None
            else:
                batch_data[batch_id] = None
                
        current_app.logger.info(f"REDIS_STORAGE: Retrieved {len(batch_ids)} batches via pipeline")
        return batch_data
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE: Error retrieving multiple batches: {e}")
        return {batch_id: None for batch_id in batch_ids}

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

def update_batch_status_optimized(batch_id: str, updates: Dict[str, Any]) -> bool:
    """Update specific fields in batch status using optimized Redis operations"""
    try:
        redis_client = get_redis_client()
        key = f"qa_batch:{batch_id}"
        
        # Use Redis pipeline for atomic operations
        pipe = redis_client.pipeline()
        pipe.get(key)
        pipe.expire(key, 604800)  # Refresh expiration
        results = pipe.execute()
        
        data = results[0]
        if data:
            batch_data = json.loads(data)
            batch_data.update(updates)
            
            # Use another pipeline to save updated data
            pipe = redis_client.pipeline()
            pipe.setex(key, 604800, json.dumps(batch_data))
            pipe.execute()
            
            current_app.logger.info(f"REDIS_STORAGE_OPT: Updated batch {batch_id}")
            return True
        else:
            current_app.logger.warning(f"REDIS_STORAGE_OPT: Cannot update non-existent batch {batch_id}")
            return False
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE_OPT: Error updating batch {batch_id}: {e}")
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

def delete_multiple_batch_status(batch_ids: List[str]) -> Dict[str, bool]:
    """Delete multiple batch assessment statuses from Redis using pipeline"""
    try:
        redis_client = get_redis_client()
        pipe = redis_client.pipeline()
        
        keys = [f"qa_batch:{batch_id}" for batch_id in batch_ids]
        for key in keys:
            pipe.delete(key)
            
        results = pipe.execute()
        
        delete_results = {}
        for i, batch_id in enumerate(batch_ids):
            delete_results[batch_id] = bool(results[i])
            
        current_app.logger.info(f"REDIS_STORAGE: Deleted {len(batch_ids)} batches via pipeline")
        return delete_results
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE: Error deleting multiple batches: {e}")
        return {batch_id: False for batch_id in batch_ids}

def list_all_batches() -> Dict[str, Dict[str, Any]]:
    """List all batch assessment statuses (for debugging)"""
    try:
        redis_client = get_redis_client()
        keys = redis_client.keys("qa_batch:*")
        
        if not keys:
            return {}
            
        # Use pipeline for efficient retrieval
        pipe = redis_client.pipeline()
        for key in keys:
            pipe.get(key)
        results = pipe.execute()
        
        batches = {}
        for i, key in enumerate(keys):
            batch_id = key.replace("qa_batch:", "")
            if results[i]:
                try:
                    batches[batch_id] = json.loads(results[i])
                except json.JSONDecodeError:
                    current_app.logger.warning(f"REDIS_STORAGE: Invalid JSON for batch {batch_id}")
                    
        current_app.logger.info(f"REDIS_STORAGE: Found {len(batches)} batches in Redis")
        return batches
    except Exception as e:
        current_app.logger.error(f"REDIS_STORAGE: Error listing batches: {e}")
        return {}

def batch_operations_context():
    """Context manager for batch Redis operations"""
    class BatchOperationsContext:
        def __init__(self):
            self.redis_client = get_redis_client()
            self.pipe = None
            
        def __enter__(self):
            self.pipe = self.redis_client.pipeline()
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.pipe:
                try:
                    self.pipe.execute()
                except Exception as e:
                    current_app.logger.error(f"REDIS_BATCH_OPS: Error executing pipeline: {e}")
                    
        def save_batch(self, batch_id: str, batch_data: Dict[str, Any]):
            """Save batch using pipeline"""
            save_batch_status_pipeline(batch_id, batch_data, self.pipe)
            
        def update_batch(self, batch_id: str, updates: Dict[str, Any]):
            """Update batch using pipeline (simplified version)"""
            key = f"qa_batch:{batch_id}"
            # Note: This is a simplified version - for complex updates, 
            # you might need to retrieve first, then update
            self.pipe.hset(f"{key}:updates", mapping=updates)
            self.pipe.expire(f"{key}:updates", 604800)
    
    return BatchOperationsContext() 