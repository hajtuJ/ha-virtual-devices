"""Deterministic safety tests for the serialized command executor."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from custom_components.virtual_devices.gate import (
    CommandExecutorConfig,
    CommandSequence,
    CommandStep,
    CommandStepType,
    ControlActionType,
    GateCommandExecutor,
    SourceRef,
    SourceUnavailableError,
    UnsafeSequenceError,
    hold_sequence,
    pulse_sequence,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@dataclass
class FakeActions:
    """Record physical operations and expose programmable availability."""

    available: list[bool] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    activate_hook: Callable[[], Awaitable[None]] | None = None

    async def async_is_available(self, source: SourceRef) -> bool:
        del source
        return self.available.pop(0) if self.available else True

    async def async_activate(self, source: SourceRef) -> None:
        self.calls.append(("activate", source.entity_id))
        if self.activate_hook is not None:
            await self.activate_hook()

    async def async_deactivate(self, source: SourceRef) -> None:
        self.calls.append(("deactivate", source.entity_id))

    async def async_press(self, source: SourceRef) -> None:
        self.calls.append(("press", source.entity_id))


@dataclass
class FakeClock:
    """Advance monotonic time whenever the executor sleeps."""

    now: float = 0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


SWITCH = SourceRef("switch.gate", ControlActionType.SWITCH)
OPEN_SWITCH = SourceRef("switch.gate_open", ControlActionType.SWITCH)
CLOSE_SWITCH = SourceRef("switch.gate_close", ControlActionType.SWITCH)
BUTTON = SourceRef("button.gate", ControlActionType.BUTTON)


@pytest.mark.parametrize("builder", [pulse_sequence, hold_sequence])
async def test_timed_switch_semantics_and_order(
    builder: Callable[[str, SourceRef, int], CommandSequence],
) -> None:
    """Pulse and bounded HOLD activate, wait, and deactivate in order."""
    actions = FakeActions()
    clock = FakeClock()
    executor = GateCommandExecutor(
        actions, sleep=clock.sleep, monotonic=clock.monotonic
    )

    await executor.async_execute(builder("move", SWITCH, 250))

    assert actions.calls == [
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
    ]
    assert clock.sleeps == [0.25]


async def test_button_source_is_pressed() -> None:
    """The MVP button adapter operation is represented by PRESS."""
    actions = FakeActions()
    sequence = CommandSequence(
        "press", (CommandStep(CommandStepType.PRESS, source=BUTTON),)
    )
    await GateCommandExecutor(actions).async_execute(sequence)
    assert actions.calls == [("press", "button.gate")]


async def test_cancellation_during_delay_always_deactivates_owned_output() -> None:
    """Cancellation cannot leave a pulse or HOLD output active."""
    actions = FakeActions()
    sleep_started = asyncio.Event()

    async def blocking_sleep(seconds: float) -> None:
        del seconds
        sleep_started.set()
        await asyncio.Event().wait()

    executor = GateCommandExecutor(actions, sleep=blocking_sleep)
    task = asyncio.create_task(
        executor.async_execute(pulse_sequence("pulse", SWITCH, 500))
    )
    await sleep_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert actions.calls[-1] == ("deactivate", "switch.gate")


async def test_activation_exception_still_deactivates_possibly_owned_output() -> None:
    """A failed activation call is treated as possibly active and cleaned up."""
    actions = FakeActions()

    async def fail_activation() -> None:
        msg = "controller failed after relay activation"
        raise RuntimeError(msg)

    actions.activate_hook = fail_activation
    executor = GateCommandExecutor(actions)

    with pytest.raises(RuntimeError, match="controller failed"):
        await executor.async_execute(pulse_sequence("pulse", SWITCH, 100))
    assert actions.calls == [
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
    ]


async def test_sequences_are_serialized_under_concurrency() -> None:
    """A second command cannot perform a physical action before the first ends."""
    actions = FakeActions()
    first_activate_started = asyncio.Event()
    release_first = asyncio.Event()

    async def block_first_activate() -> None:
        first_activate_started.set()
        await release_first.wait()
        actions.activate_hook = None

    actions.activate_hook = block_first_activate
    executor = GateCommandExecutor(actions)
    first = asyncio.create_task(
        executor.async_execute(pulse_sequence("first", SWITCH, 1))
    )
    await first_activate_started.wait()
    second = asyncio.create_task(
        executor.async_execute(pulse_sequence("second", SWITCH, 1))
    )
    await asyncio.sleep(0)
    assert actions.calls == [("activate", "switch.gate")]

    release_first.set()
    await asyncio.gather(first, second)
    assert actions.calls == [
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
    ]


async def test_preflight_rejects_unavailable_source_before_any_action() -> None:
    """A known-invalid sequence never starts partially."""
    actions = FakeActions(available=[False])
    executor = GateCommandExecutor(actions)
    with pytest.raises(SourceUnavailableError, match="unavailable"):
        await executor.async_execute(pulse_sequence("pulse", SWITCH, 100))
    assert actions.calls == []


async def test_mid_sequence_unavailability_aborts_and_cleans_up() -> None:
    """A source loss after activation still forces best-effort deactivation."""
    actions = FakeActions(available=[True, True, False])
    clock = FakeClock()
    executor = GateCommandExecutor(
        actions, sleep=clock.sleep, monotonic=clock.monotonic
    )
    with pytest.raises(SourceUnavailableError, match="became unavailable"):
        await executor.async_execute(pulse_sequence("pulse", SWITCH, 100))
    assert actions.calls == [
        ("activate", "switch.gate"),
        ("deactivate", "switch.gate"),
    ]


async def test_mutually_exclusive_outputs_never_overlap() -> None:
    """A sequence cannot activate OPEN while CLOSE is still owned."""
    actions = FakeActions()
    sequence = CommandSequence(
        "unsafe reversal",
        (
            CommandStep(CommandStepType.ACTIVATE, source=OPEN_SWITCH),
            CommandStep(CommandStepType.ACTIVATE, source=CLOSE_SWITCH),
        ),
    )
    config = CommandExecutorConfig(
        mutually_exclusive_groups=(frozenset({OPEN_SWITCH, CLOSE_SWITCH}),)
    )
    with pytest.raises(UnsafeSequenceError, match="mutually exclusive"):
        await GateCommandExecutor(actions, config).async_execute(sequence)
    assert actions.calls == [
        ("activate", "switch.gate_open"),
        ("deactivate", "switch.gate_open"),
    ]


async def test_minimum_command_and_action_intervals_are_enforced() -> None:
    """Only the remaining interval is delayed between physical operations."""
    actions = FakeActions()
    clock = FakeClock()
    config = CommandExecutorConfig(
        minimum_command_interval_ms=1000,
        minimum_action_interval_ms=250,
    )
    executor = GateCommandExecutor(
        actions, config, sleep=clock.sleep, monotonic=clock.monotonic
    )

    await executor.async_execute(pulse_sequence("first", SWITCH, 100))
    await executor.async_execute(
        CommandSequence("second", (CommandStep(CommandStepType.PRESS, source=BUTTON),))
    )

    assert clock.sleeps == pytest.approx([0.1, 0.15, 0.75])
    assert actions.calls[-1] == ("press", "button.gate")


def test_executor_configuration_rejects_invalid_safety_values() -> None:
    """Negative intervals and one-member interlocks are invalid."""
    with pytest.raises(ValueError, match="cannot be negative"):
        CommandExecutorConfig(minimum_command_interval_ms=-1)
    with pytest.raises(ValueError, match="at least two"):
        CommandExecutorConfig(mutually_exclusive_groups=(frozenset({OPEN_SWITCH}),))
