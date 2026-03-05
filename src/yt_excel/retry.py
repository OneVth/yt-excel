"""Common retry utility with exponential backoff and jitter."""

import functools
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# Default retry parameters from design doc (Section 12.1)
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_JITTER = 0.5  # seconds


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted.

    Attributes:
        last_exception: The exception from the final attempt.
        attempts: Total number of attempts made.
    """

    def __init__(self, last_exception: Exception, attempts: int) -> None:
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(
            f"All {attempts} attempts failed. Last error: {last_exception}"
        )


def with_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_jitter: float = DEFAULT_MAX_JITTER,
    retryable: tuple[type[Exception], ...] = (Exception,),
    backoff: str = "exponential",
) -> Callable[[F], F]:
    """Decorator for retrying a function with exponential backoff and jitter.

    Exponential backoff: base_delay * 2^(attempt - 1)
    Jitter: random 0 ~ max_jitter seconds added to each delay.

    Args:
        max_retries: Maximum number of retry attempts (not counting the initial call).
        base_delay: Base delay in seconds for the first retry.
        max_jitter: Maximum random jitter in seconds added to each delay.
        retryable: Tuple of exception types that trigger a retry.
        backoff: Backoff strategy. "exponential" or "fixed".

    Returns:
        Decorated function with retry behavior.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            total_attempts = 1 + max_retries

            for attempt in range(1, total_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable as exc:
                    last_exc = exc
                    if attempt == total_attempts:
                        raise RetryExhaustedError(exc, total_attempts) from exc

                    if backoff == "exponential":
                        delay = base_delay * (2 ** (attempt - 1))
                    else:
                        delay = base_delay

                    jitter = random.uniform(0, max_jitter)
                    time.sleep(delay + jitter)

        return wrapper  # type: ignore[return-value]

    return decorator
