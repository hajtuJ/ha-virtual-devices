"""Deterministic tests for gate position estimation."""

from dataclasses import dataclass

import pytest
from custom_components.virtual_devices.gate import (
    GateDirection,
    GatePositionEstimator,
)


@dataclass
class FakeClock:
    """Controllable monotonic clock."""

    now: float = 0

    def monotonic(self) -> float:
        return self.now


def test_independent_opening_and_closing_estimates() -> None:
    clock = FakeClock()
    estimator = GatePositionEstimator(10_000, 20_000, monotonic=clock.monotonic)

    estimator.start(GateDirection.OPENING, 0)
    clock.now = 5
    assert estimator.position == pytest.approx(50)
    assert estimator.freeze() == pytest.approx(50)

    estimator.start(GateDirection.CLOSING, 100)
    clock.now = 15
    assert estimator.position == pytest.approx(50)


def test_freeze_restore_clamp_and_endpoint_calibration() -> None:
    clock = FakeClock()
    estimator = GatePositionEstimator(1_000, 1_000, monotonic=clock.monotonic)
    estimator.restore(47)
    assert estimator.position == 47

    estimator.start(GateDirection.OPENING, 47)
    clock.now = 100
    assert estimator.position == 100
    assert estimator.calibrate(0) == 0
    assert estimator.position == 0

    estimator.restore(120)
    assert estimator.position == 100


def test_unknown_position_stays_unknown_during_unanchored_motion() -> None:
    estimator = GatePositionEstimator(10_000, 10_000)
    estimator.start(GateDirection.OPENING, None)
    assert estimator.position is None
    assert estimator.freeze() is None
