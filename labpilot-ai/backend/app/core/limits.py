from app.config import get_settings
from app.core.ratelimit import SlidingWindowLimiter

_s = get_settings()
login_failures = SlidingWindowLimiter(_s.login_max_failures, _s.login_window_seconds)
execution_limiter = SlidingWindowLimiter(_s.exec_max_per_minute, 60)


def reset_all() -> None:
    login_failures.reset()
    execution_limiter.reset()
