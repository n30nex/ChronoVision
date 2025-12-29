import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, rpm: int, max_attempts: int, base_delay: int, circuit_threshold: int):
        self.rpm = max(1, rpm)
        self.max_attempts = max(1, max_attempts)
        self.base_delay = max(1, base_delay)
        self.circuit_threshold = max(1, circuit_threshold)
        self.timestamps = deque()
        self.lock = threading.Lock()
        self.failure_count = 0
        self.circuit_open_until = 0.0

    def acquire(self) -> None:
        while True:
            sleep_for = 0.0
            with self.lock:
                now = time.time()
                self._prune(now)
                if self.circuit_open_until > now:
                    sleep_for = self.circuit_open_until - now
                elif len(self.timestamps) >= self.rpm:
                    sleep_for = 60 - (now - self.timestamps[0])
                else:
                    self.timestamps.append(now)
                    return
            if sleep_for > 0:
                time.sleep(sleep_for)

    def record_success(self) -> None:
        with self.lock:
            self.failure_count = 0
            self.circuit_open_until = 0.0

    def record_failure(self) -> None:
        with self.lock:
            self.failure_count += 1
            if self.failure_count >= self.circuit_threshold:
                self.circuit_open_until = time.time() + max(30, self.base_delay * 5)
                self.failure_count = 0

    def backoff(self, attempt: int) -> None:
        delay = self.base_delay * (2 ** max(0, attempt - 1))
        time.sleep(delay)

    def _prune(self, now: float) -> None:
        while self.timestamps and (now - self.timestamps[0]) > 60:
            self.timestamps.popleft()
