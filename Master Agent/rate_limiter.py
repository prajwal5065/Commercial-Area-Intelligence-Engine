"""
rate_limiter.py — Global API Rate Limiter
================================================================
Prevents 432 (Tavily) and 429 (Groq) errors by enforcing a global rate limit
across ALL threads automatically. No more guessing with time.sleep() needed.
"""

import time
import threading

class RateLimiter:
    def __init__(self, max_per_second: float = 1.5):
        self.min_interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last_time = 0.0

    def wait(self):
        """Call this right before ANY Tavily or Groq API call."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_time = time.time()

# Create 2 global limiters (one for Tavily, one for Groq)
# Tavily allows ~2 requests/sec. We use 1.5/sec to be safe.
tavily_limiter = RateLimiter(max_per_second=1.5)
# Groq free tier allows ~30 req/min. We use 2 req/sec to be safe.
groq_limiter = RateLimiter(max_per_second=2.0)