"""
rate_limiter.py — Global API Rate Limiter
"""
import time
import threading
import os
import sys

class RateLimiter:
    def __init__(self, max_per_second: float = 1.5, lock_name: str = "global"):
        self.min_interval = 1.0 / max_per_second
        self._thread_lock = threading.Lock()
        
        # File paths for cross-process locking and state
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self._lock_file = os.path.join(base_dir, f".{lock_name}_rate.lock")
        self._time_file = os.path.join(base_dir, f".{lock_name}_last_time.txt")
        
        # Initialize files if they don't exist
        if not os.path.exists(self._lock_file):
            with open(self._lock_file, "w") as f: f.write("0")
        if not os.path.exists(self._time_file):
            with open(self._time_file, "w") as f: f.write("0.0")

    def wait(self):
        """Call this right BEFORE any API call. Safe for threads and processes."""
        with self._thread_lock:
            # Cross-process lock using msvcrt (Windows only, matching OS)
            if sys.platform == "win32":
                import msvcrt
                f = open(self._lock_file, "w")
                while True:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
            else:
                # Fallback for Linux/Mac using fcntl
                import fcntl
                f = open(self._lock_file, "w")
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
            try:
                # Read the last request time across all processes
                last_time = 0.0
                try:
                    with open(self._time_file, "r") as tf:
                        val = tf.read().strip()
                        if val:
                            last_time = float(val)
                except Exception:
                    pass
                
                now = time.time()
                elapsed = now - last_time
                if elapsed < self.min_interval:
                    time.sleep(self.min_interval - elapsed)
                    now = time.time()
                
                # Update the last request time
                with open(self._time_file, "w") as tf:
                    tf.write(str(now))
                    
            finally:
                if sys.platform == "win32":
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                f.close()

# Tavily allows ~2/sec, we use 1.5/sec to be safe
tavily_limiter = RateLimiter(max_per_second=1.5, lock_name="tavily")
# Groq free tier allows ~30/min, we use 2/sec to be safe
groq_limiter = RateLimiter(max_per_second=2.0, lock_name="groq")
# Gemini free tier is 15 RPM. We use 14/min to be safe globally across all agents.
gemini_limiter = RateLimiter(max_per_second=14.0/60.0, lock_name="gemini")