import time

from app.rate_limiter import RateLimiter


def test_rate_limiter_circuit_opens():
    limiter = RateLimiter(rpm=60, max_attempts=1, base_delay=1, circuit_threshold=1)
    limiter.record_failure()
    assert limiter.circuit_open_until >= time.time()
