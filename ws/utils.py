import asyncio
import functools
import logging
from typing import Callable, Any, Coroutine

logger = logging.getLogger(__name__)

def run_async_safely(coroutine_func: Callable[..., Coroutine]) -> Callable:
    """
    Decorator to safely run async functions, particularly for WebSocket operations,
    in both async and sync contexts.
    
    This prevents "no running event loop" errors when WebSocket functions
    are called from synchronous code.
    
    Usage:
        @run_async_safely
        async def my_async_function():
            pass
    """
    @functools.wraps(coroutine_func)
    def wrapper(*args, **kwargs):
        try:
            # If we're already in an async context and event loop is running
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the coroutine in the running loop
                    return asyncio.create_task(coroutine_func(*args, **kwargs))
                else:
                    # Run the coroutine in the existing loop
                    return asyncio.run_coroutine_threadsafe(
                        coroutine_func(*args, **kwargs), loop
                    )
            except RuntimeError:
                # No event loop in this thread, create a new one
                return asyncio.run(coroutine_func(*args, **kwargs))
        except Exception as e:
            # Log any errors but don't propagate them to prevent app crashes
            logger.error(f"Error running async function {coroutine_func.__name__}: {str(e)}")
            return None
    
    return wrapper

def safe_async_call(coroutine, fallback_value=None):
    """
    Safely executes an asyncio coroutine from a synchronous context.
    
    Args:
        coroutine: The coroutine to execute
        fallback_value: Value to return if execution fails
    
    Returns:
        Result of the coroutine if successful, fallback_value otherwise
    """
    try:
        # Try to get the current event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If there's a running loop, create a future but don't wait
                future = asyncio.run_coroutine_threadsafe(coroutine, loop)
                # Return the fallback immediately - the coroutine runs in the background
                return fallback_value
            else:
                # Run in the existing loop
                return loop.run_until_complete(coroutine)
        except RuntimeError:
            # No event loop, create a new one
            return asyncio.run(coroutine)
    except Exception as e:
        logger.error(f"Error in safe_async_call: {str(e)}")
        return fallback_value
