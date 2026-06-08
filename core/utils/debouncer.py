"""
Debouncer utility for reducing file I/O operations.
"""
import asyncio
import time
from typing import Callable, Dict, Any


class Debouncer:
    """
    Debounces function calls to reduce frequent operations.
    Useful for file writes, database commits, etc.
    """
    def __init__(self, delay: float = 5.0, max_delay: float = 30.0):
        """
        Args:
            delay: Minimum time (seconds) between calls
            max_delay: Maximum time to wait before forcing a call
        """
        self.delay = delay
        self.max_delay = max_delay
        self.last_call = 0.0
        self.first_pending = None
        self.pending_task = None
        self.is_dirty = False
    
    def mark_dirty(self):
        """Mark that data has changed and needs to be saved."""
        self.is_dirty = True
        if self.first_pending is None:
            self.first_pending = time.time()
    
    async def debounce(self, func: Callable, *args, **kwargs):
        """
        Schedule a debounced function call.
        Returns immediately; actual call happens after delay.
        """
        if not self.is_dirty:
            return
        
        # Cancel any pending task
        if self.pending_task and not self.pending_task.done():
            self.pending_task.cancel()
        
        # Calculate wait time
        now = time.time()
        time_since_last = now - self.last_call
        time_since_first = now - (self.first_pending or now)
        
        # Force immediate call if max_delay reached
        if time_since_first >= self.max_delay:
            await self._execute(func, *args, **kwargs)
            return
        
        # Schedule delayed call
        wait_time = max(0, self.delay - time_since_last)
        self.pending_task = asyncio.create_task(self._delayed_execute(wait_time, func, *args, **kwargs))
    
    async def _delayed_execute(self, wait_time: float, func: Callable, *args, **kwargs):
        """Wait and then execute."""
        try:
            await asyncio.sleep(wait_time)
            await self._execute(func, *args, **kwargs)
        except asyncio.CancelledError:
            pass  # Task was cancelled, that's fine
    
    async def _execute(self, func: Callable, *args, **kwargs):
        """Execute the function and reset state."""
        if not self.is_dirty:
            return
        
        try:
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                await asyncio.to_thread(func, *args, **kwargs)
            
            self.last_call = time.time()
            self.first_pending = None
            self.is_dirty = False
        except Exception as e:
            # Log but don't crash
            import logging
            logging.getLogger(__name__).error(f"Debounced function failed: {e}")
    
    async def flush(self, func: Callable, *args, **kwargs):
        """Force immediate execution regardless of debounce timer."""
        if not self.is_dirty:
            return
        
        # Cancel pending task
        if self.pending_task and not self.pending_task.done():
            self.pending_task.cancel()
        
        await self._execute(func, *args, **kwargs)


class SyncDebouncer:
    """Synchronous version of Debouncer for non-async contexts."""
    def __init__(self, delay: float = 5.0, max_delay: float = 30.0):
        self.delay = delay
        self.max_delay = max_delay
        self.last_call = 0.0
        self.first_pending = None
        self.is_dirty = False
    
    def mark_dirty(self):
        """Mark that data has changed."""
        self.is_dirty = True
        if self.first_pending is None:
            self.first_pending = time.time()
    
    def should_save(self) -> bool:
        """Check if enough time has passed to warrant a save."""
        if not self.is_dirty:
            return False
        
        now = time.time()
        time_since_last = now - self.last_call
        time_since_first = now - (self.first_pending or now)
        
        # Save if either condition met
        return time_since_last >= self.delay or time_since_first >= self.max_delay
    
    def execute(self, func: Callable, *args, **kwargs):
        """Execute if conditions are met."""
        if self.should_save():
            try:
                func(*args, **kwargs)
                self.last_call = time.time()
                self.first_pending = None
                self.is_dirty = False
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Debounced function failed: {e}")
    
    def flush(self, func: Callable, *args, **kwargs):
        """Force immediate execution."""
        if self.is_dirty:
            try:
                func(*args, **kwargs)
                self.last_call = time.time()
                self.first_pending = None
                self.is_dirty = False
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Flush failed: {e}")
