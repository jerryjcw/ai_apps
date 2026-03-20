"""Configurable retry with fixed or exponential backoff."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RetryConfig:
    """Retry strategy configuration.

    Parameters
    ----------
    max_attempts : int
        Total attempts (1 = no retries).
    strategy : ``"fixed"`` | ``"exponential"``
        ``"fixed"`` waits ``base_delay`` every time.
        ``"exponential"`` doubles the wait each attempt, adds jitter,
        and caps at ``max_delay``.
    base_delay : float
        Seconds to wait on the first retry (fixed) or the base of the
        exponential curve.
    max_delay : float
        Upper bound on the computed delay (only meaningful for
        ``"exponential"``).
    """

    max_attempts: int = 5
    strategy: Literal["fixed", "exponential"] = "exponential"
    base_delay: float = 2.0
    max_delay: float = 60.0

    def delay(self, attempt: int) -> float:
        """Compute the wait time in seconds for the given *attempt* (0-based).

        Fixed:       ``base_delay``
        Exponential: ``min(base_delay * 2^attempt, max_delay) + jitter``
        """
        if self.strategy == "fixed":
            return self.base_delay
        d = min(self.base_delay * (2 ** attempt), self.max_delay)
        return d + random.uniform(0, d / 2)
