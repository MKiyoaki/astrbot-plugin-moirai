import time
import asyncio
from collections import deque
from typing import Dict, List

class PerfTracker:
    """Tracks average execution time for various system phases.
    
    Maintains a rolling window of recent execution times to provide 
    stable averages for monitoring.
    """
    
    def __init__(self, window_size: int = 50):
        self._history: Dict[str, deque] = {
            "extraction": deque(maxlen=window_size),
            "partition": deque(maxlen=window_size),
            "distill": deque(maxlen=window_size),
            "retrieval": deque(maxlen=window_size),
            "recall": deque(maxlen=window_size),
        }
        self._lock = asyncio.Lock()

    async def record(self, phase: str, duration: float):
        """Record the duration of a specific phase."""
        if phase not in self._history:
            return
        async with self._lock:
            self._history[phase].append(duration)

    async def get_averages(self) -> Dict[str, float]:
        """Return the average duration for all tracked phases."""
        async with self._lock:
            return {
                phase: (sum(times) / len(times)) if times else 0.0
                for phase, times in self._history.items()
            }

# Global singleton for system-wide access
tracker = PerfTracker()

class performance_timer:
    """Context manager for timing asynchronous operations."""
    def __init__(self, phase: str):
        self.phase = phase
        self.start_time = None

    async def __aenter__(self):
        self.start_time = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start_time
        await tracker.record(self.phase, duration)
