import time
import asyncio
from collections import deque
from typing import Dict, List, Optional

class PerfTracker:
    """Tracks execution time and hit rates for various system phases.
    
    Maintains a rolling window of recent execution times and hit counts
    to provide stable metrics for monitoring.
    """
    
    def __init__(self, window_size: int = 50):
        self._history: Dict[str, deque] = {}
        self._last_durations: Dict[str, float] = {}
        self._hit_history: Dict[str, deque] = {}
        self._window_size = window_size
        self._lock = asyncio.Lock()

    async def record(self, phase: str, duration: float):
        """Record the duration of a specific phase."""
        async with self._lock:
            if phase not in self._history:
                self._history[phase] = deque(maxlen=self._window_size)
            self._history[phase].append(duration)
            self._last_durations[phase] = duration

    async def record_hit(self, phase: str, hit_count: int):
        """Record hit/recall count for a specific phase."""
        async with self._lock:
            if phase not in self._hit_history:
                self._hit_history[phase] = deque(maxlen=self._window_size)
            self._hit_history[phase].append(hit_count)

    async def get_metrics(self) -> Dict[str, Dict[str, float]]:
        """Return averages, last durations, and hit rates for all tracked phases."""
        async with self._lock:
            metrics = {}
            # Durations
            for phase, times in self._history.items():
                if phase not in metrics: metrics[phase] = {}
                metrics[phase]["avg"] = (sum(times) / len(times)) if times else 0.0
                metrics[phase]["last"] = self._last_durations.get(phase, 0.0)
            
            # Hit Rates
            for phase, counts in self._hit_history.items():
                if phase not in metrics: metrics[phase] = {}
                metrics[phase]["avg_hits"] = (sum(counts) / len(counts)) if counts else 0.0
                metrics[phase]["last_hits"] = counts[-1] if counts else 0
                
            return metrics

    async def get_averages(self) -> Dict[str, float]:
        """Backward compatibility for existing API."""
        m = await self.get_metrics()
        return {p: v.get("avg", 0.0) for p, v in m.items()}

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
