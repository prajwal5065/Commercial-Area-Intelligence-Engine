"""
rate_limiter.py — Global API Rate Limiter
"""
import time
import threading

class RateLimiter:
    def __init__(self, max_per_second: float = 1.5):
        self.min_interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last_time = 0.0

    def wait(self):
        """Call this right BEFORE any Tavily or Groq API call."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_time = time.time()

# Tavily allows ~2/sec, we use 1.5/sec to be safe
tavily_limiter = RateLimiter(max_per_second=1.5)
# Groq free tier allows ~30/min, we use 2/sec to be safe
groq_limiter = RateLimiter(max_per_second=2.0)