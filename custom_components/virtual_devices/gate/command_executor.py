"""Serialized and cancellation-safe physical command execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from .command_models import CommandSequence, CommandStep, CommandStepType, SourceRef

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class ConcurrentCommandPolicy(StrEnum):
    """Supported behavior for a command received during execution."""

    QUEUE = "queue"


class SourceUnavailableError(RuntimeError):
    """Raised before using a source that is not currently available."""


class UnsafeSequenceError(RuntimeError):
    """Raised when a sequence would activate mutually exclusive outputs."""


class SourceActions(Protocol):
    """Minimal adapter contract between the executor and Home Assistant."""

    async def async_is_available(self, source: SourceRef) -> bool:
        """Return whether the source may be called now."""

    async def async_activate(self, source: SourceRef) -> None:
        """Activate a switch source."""

    async def async_deactivate(self, source: SourceRef) -> None:
        """Deactivate a switch source."""

    async def async_press(self, source: SourceRef) -> None:
        """Press a button source."""


@dataclass(frozen=True, slots=True)
class CommandExecutorConfig:
    """Timing and interlock settings for one gate executor."""

    minimum_command_interval_ms: int = 0
    minimum_action_interval_ms: int = 0
    concurrent_policy: ConcurrentCommandPolicy = ConcurrentCommandPolicy.QUEUE
    mutually_exclusive_groups: tuple[frozenset[SourceRef], ...] = ()

    def __post_init__(self) -> None:
        """Reject timing and interlock settings that cannot be enforced."""
        if self.minimum_command_interval_ms < 0:
            msg = "minimum_command_interval_ms cannot be negative"
            raise ValueError(msg)
        if self.minimum_action_interval_ms < 0:
            msg = "minimum_action_interval_ms cannot be negative"
            raise ValueError(msg)
        if any(len(group) < 2 for group in self.mutually_exclusive_groups):
            msg = "mutually exclusive groups require at least two sources"
            raise ValueError(msg)


def pulse_sequence(name: str, source: SourceRef, duration_ms: int) -> CommandSequence:
    """Build an activate-delay-deactivate pulse sequence."""
    return _timed_switch_sequence(name, source, duration_ms)


def hold_sequence(name: str, source: SourceRef, duration_ms: int) -> CommandSequence:
    """Build a bounded HOLD with the same guaranteed cleanup semantics."""
    return _timed_switch_sequence(name, source, duration_ms)


def _timed_switch_sequence(
    name: str, source: SourceRef, duration_ms: int
) -> CommandSequence:
    """Build the validated atomic steps shared by pulses and bounded holds."""
    return CommandSequence(
        name=name,
        steps=(
            CommandStep(CommandStepType.ACTIVATE, source=source),
            CommandStep(CommandStepType.DELAY, duration_ms=duration_ms),
            CommandStep(CommandStepType.DEACTIVATE, source=source),
        ),
    )


class GateCommandExecutor:
    """Execute exactly one validated physical command sequence at a time."""

    def __init__(
        self,
        actions: SourceActions,
        config: CommandExecutorConfig | None = None,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        """Initialize an executor with injectable timing for deterministic tests."""
        self._actions = actions
        self._config = config or CommandExecutorConfig()
        self._sleep = sleep
        self._monotonic = monotonic or asyncio.get_running_loop().time
        self._lock = asyncio.Lock()
        self._last_command_at: float | None = None
        self._last_action_at: float | None = None

    async def async_execute(self, sequence: CommandSequence) -> None:
        """Queue and execute a sequence with preflight and final cleanup."""
        async with self._lock:
            await self._preflight(sequence)
            await self._wait_for_interval(
                self._last_command_at,
                self._config.minimum_command_interval_ms,
            )
            self._last_command_at = self._monotonic()
            await self._execute_locked(sequence)

    async def _preflight(self, sequence: CommandSequence) -> None:
        """Validate all critical sources before the first physical action."""
        sources = {step.source for step in sequence.steps if step.source is not None}
        for source in sources:
            if not await self._actions.async_is_available(source):
                msg = f"source is unavailable: {source.entity_id}"
                raise SourceUnavailableError(msg)

    async def _execute_locked(self, sequence: CommandSequence) -> None:
        """Run steps while tracking every output owned by this execution."""
        active: set[SourceRef] = set()
        activation_order: list[SourceRef] = []
        try:
            for step in sequence.steps:
                if step.type is CommandStepType.DELAY:
                    await self._sleep(self._duration_seconds(step))
                    continue

                source = self._required_source(step)
                if not await self._actions.async_is_available(source):
                    msg = f"source became unavailable: {source.entity_id}"
                    raise SourceUnavailableError(msg)

                await self._wait_for_interval(
                    self._last_action_at,
                    self._config.minimum_action_interval_ms,
                )
                if step.type is CommandStepType.ACTIVATE:
                    self._assert_not_mutually_exclusive(source, active)
                    if source not in active:
                        active.add(source)
                        activation_order.append(source)
                    await self._actions.async_activate(source)
                elif step.type is CommandStepType.DEACTIVATE:
                    await self._actions.async_deactivate(source)
                    active.discard(source)
                else:
                    await self._actions.async_press(source)
                self._last_action_at = self._monotonic()
        finally:
            for source in reversed(activation_order):
                if source not in active:
                    continue
                try:
                    await self._actions.async_deactivate(source)
                finally:
                    active.discard(source)

    def _assert_not_mutually_exclusive(
        self, source: SourceRef, active: set[SourceRef]
    ) -> None:
        """Prevent overlap of configured direction outputs."""
        for group in self._config.mutually_exclusive_groups:
            if source in group and not active.isdisjoint(group - {source}):
                msg = f"mutually exclusive source already active: {source.entity_id}"
                raise UnsafeSequenceError(msg)

    async def _wait_for_interval(self, previous: float | None, minimum_ms: int) -> None:
        """Wait only for the remaining part of a configured interval."""
        if previous is None or minimum_ms == 0:
            return
        remaining = minimum_ms / 1000 - (self._monotonic() - previous)
        if remaining > 0:
            await self._sleep(remaining)

    @staticmethod
    def _duration_seconds(step: CommandStep) -> float:
        """Return the validated delay duration in seconds."""
        if step.duration_ms is None:
            msg = "delay step has no duration"
            raise ValueError(msg)
        return step.duration_ms / 1000

    @staticmethod
    def _required_source(step: CommandStep) -> SourceRef:
        """Return the validated source carried by a physical action step."""
        if step.source is None:
            msg = "physical action step has no source"
            raise ValueError(msg)
        return step.source
