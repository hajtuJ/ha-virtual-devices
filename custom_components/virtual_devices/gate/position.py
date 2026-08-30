"""Deterministic position estimation for Virtual Gate."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from .models import GateDirection


class GatePositionEstimator:
    """Estimate and freeze gate position using an injectable monotonic clock."""

    def __init__(
        self,
        opening_time_ms: int,
        closing_time_ms: int,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize independent opening and closing travel durations."""
        if opening_time_ms <= 0 or closing_time_ms <= 0:
            raise ValueError("travel times must be positive")
        self._opening_seconds = opening_time_ms / 1000
        self._closing_seconds = closing_time_ms / 1000
        self._monotonic = monotonic
        self._position: float | None = None
        self._start_position: float | None = None
        self._started_at: float | None = None
        self._direction = GateDirection.UNKNOWN

    @property
    def position(self) -> float | None:
        """Return the current estimate without changing estimator state."""
        if self._started_at is None or self._start_position is None:
            return self._position
        elapsed = max(0.0, self._monotonic() - self._started_at)
        if self._direction is GateDirection.OPENING:
            value = self._start_position + elapsed / self._opening_seconds * 100
        elif self._direction is GateDirection.CLOSING:
            value = self._start_position - elapsed / self._closing_seconds * 100
        else:
            value = self._start_position
        return max(0.0, min(100.0, value))

    def restore(self, position: float | None) -> None:
        """Restore a frozen estimate without resuming movement."""
        self._position = self._clamp(position)
        self._start_position = None
        self._started_at = None
        self._direction = GateDirection.UNKNOWN

    def start(self, direction: GateDirection, position: float | None) -> None:
        """Begin estimating from a known position, if available."""
        if direction is GateDirection.UNKNOWN:
            raise ValueError("movement requires a known direction")
        self._position = self._clamp(position)
        self._start_position = self._position
        self._started_at = self._monotonic() if self._position is not None else None
        self._direction = direction

    def freeze(self) -> float | None:
        """Freeze and return the current position estimate."""
        self._position = self.position
        self._start_position = None
        self._started_at = None
        self._direction = GateDirection.UNKNOWN
        return self._position

    def calibrate(self, position: float) -> float:
        """Apply an authoritative physical endpoint."""
        calibrated = self._clamp(position)
        if calibrated is None:
            raise ValueError("endpoint position is required")
        self.restore(calibrated)
        return calibrated

    @staticmethod
    def _clamp(position: float | None) -> float | None:
        if position is None:
            return None
        return max(0.0, min(100.0, float(position)))
