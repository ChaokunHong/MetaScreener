"""
API Rate Limiter for MetaScreener

This module provides utilities to handle API rate limiting to prevent 429 errors
when making many parallel requests to LLM APIs.
"""

import time
import logging
from gevent.pool import Pool
from gevent import sleep, spawn

# Setup logging
limiter_logger = logging.getLogger("rate_limiter")

class APIRateLimiter:
    """
    Manages API request rate limiting to prevent 429 Too Many Requests errors.
    Uses a combination of:
    1. Concurrency limiting (max parallel requests)
    2. Request spacing (delay between requests in same pool)
    """
    
    def __init__(self, max_concurrent=50, request_interval=0.0):
        """
        Initialize the rate limiter.
        
        Args:
            max_concurrent: Maximum number of concurrent requests (pool size)
            request_interval: Not used anymore, kept for compatibility
        """
        self.max_concurrent = max_concurrent
        self.request_interval = request_interval  # Not used anymore
        self.pool = Pool(max_concurrent)
        self.last_request_time = 0
        
    def process_batch(self, items, process_func, *args, **kwargs):
        """
        Process a batch of items with rate limiting.
        
        Args:
            items: List of items to process
            process_func: Function to call for each item
            *args, **kwargs: Additional arguments to pass to process_func
            
        Returns:
            List of results in the same order as the input items
        """
        limiter_logger.info(f"Processing batch of {len(items)} items with max concurrency {self.max_concurrent}")
        results = []
        
        for item in items:
            # Ensure we don't exceed rate limits
            self._wait_for_rate_limit()
            
            # Queue the job in the pool
            results.append(self.pool.spawn(process_func, item, *args, **kwargs))
            
        # Wait for all jobs to complete
        self.pool.join()
        
        # Return actual results (not greenlets)
        return [greenlet.get() for greenlet in results]
    
    def process_items_with_callback(self, items, process_func, callback_func=None, *args, **kwargs):
        """
        Process items with rate limiting and call a callback for each completed item.
        Useful for streaming progress updates.
        
        Args:
            items: List of items to process
            process_func: Function to call for each item
            callback_func: Function to call with each result (optional)
            *args, **kwargs: Additional arguments to pass to process_func
        """
        limiter_logger.info(f"Processing {len(items)} items with callback, max concurrency {self.max_concurrent}")
        greenlets = []
        completed_count = 0
        total_items = len(items)
        
        # Set smaller batch size for callbacks to improve UI responsiveness
        callback_batch_size = min(5, max(1, self.max_concurrent // 10))
        
        for idx, item in enumerate(items):
            # Ensure we don't exceed rate limits
            self._wait_for_rate_limit()
            
            # Create a job that will call the callback when done
            def job_with_callback(item_data, item_idx):
                result = process_func(item_data, *args, **kwargs)
                if callback_func:
                    # Minimal delay for UI responsiveness - reduced from previous version
                    sleep(0.001)  # Minimal sleep to allow event loop to process UI updates
                    callback_func(item_data, result)
                return result
            
            # Queue the job in the pool
            greenlets.append(self.pool.spawn(job_with_callback, item, idx))
            
            # For better UI responsiveness, force periodic yield to event loop
            # after spawning a small batch of jobs
            if (idx + 1) % callback_batch_size == 0:
                # This tiny sleep allows the event loop to process UI events
                sleep(0.001)
                
                # Check if any greenlets have completed and process them
                newly_completed = 0
                for g in list(greenlets):
                    if g.ready():
                        newly_completed += 1
                
                if newly_completed > 0:
                    completed_count += newly_completed
                    limiter_logger.debug(f"Progress update: {completed_count}/{total_items} items completed")
        
        # Wait for all jobs to complete
        self.pool.join()
        
        return [g.get() for g in greenlets]
    
    def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limits"""
        # Check if we need to wait for pool slot - only minimal waiting
        # This is the only limit we keep, as it's required for the Pool to function
        while self.pool.full():
            sleep(0.005)  # Reduced sleep time for better responsiveness
        
        # No longer enforcing time delay between requests
        # Simply update the last_request_time for tracking
        self.last_request_time = time.time()