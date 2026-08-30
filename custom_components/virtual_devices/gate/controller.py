"""Runtime orchestration for one Virtual Gate."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.exceptions import ServiceValidationError

from ..const import DOMAIN
from .command_executor import (
    CommandExecutorConfig,
    GateCommandExecutor,
    SourceActions,
    SourceUnavailableError,
)
from .command_models import CommandSequence, CommandStep, CommandStepType, SourceRef
from .models import (
    ControlActionType,
    DirectionChangeStrategyType,
    GateCommand,
    GateDirection,
    GateEffect,
    GateEffectType,
    GateEvent,
    GateEventType,
    GateProblem,
    GateSnapshot,
    RepeatedCommandPolicy,
    StopStrategyType,
)
from .state_machine import GateStateMachine, GateStateMachineConfig, LimitSensorConfig

if TYPE_CHECKING:
    from .config import GateConfig

type UpdateCallback = Callable[[], None]


class GateController:
    """Coordinate pure transitions and serialized physical command effects."""

    def __init__(
        self,
        config: GateConfig,
        actions: SourceActions,
        *,
        initial_snapshot: GateSnapshot | None = None,
    ) -> None:
        """Create a passive controller; construction never executes an action."""
        self.config = config
        self._machine = GateStateMachine(
            GateStateMachineConfig(
                open_limit=LimitSensorConfig(config.open_limit.active_state)
                if config.open_limit is not None
                else None,
                closed_limit=LimitSensorConfig(config.closed_limit.active_state)
                if config.closed_limit is not None
                else None,
                stop_strategy=config.stop_strategy,
                direction_change_strategy=config.direction_change_strategy,
                repeated_open_policy=config.repeated_open_policy,
                repeated_close_policy=config.repeated_close_policy,
            )
        )
        interlocks: tuple[frozenset[SourceRef], ...] = ()
        if config.open_source is not None and config.close_source is not None:
            interlocks = (frozenset({config.open_source, config.close_source}),)
        self._executor = GateCommandExecutor(
            actions,
            CommandExecutorConfig(
                minimum_command_interval_ms=config.minimum_command_interval_ms,
                mutually_exclusive_groups=interlocks,
            ),
        )
        self._actions = actions
        self._snapshot = initial_snapshot or GateSnapshot()
        self._callbacks: set[UpdateCallback] = set()
        self._command_lock = asyncio.Lock()
        self._active_execution: asyncio.Task[None] | None = None
        self._shutdown = False

    @property
    def snapshot(self) -> GateSnapshot:
        """Return the current immutable cached domain state."""
        return self._snapshot

    @property
    def control_available(self) -> bool:
        """Return cached command availability independently of logical state."""
        return self._snapshot.source_available and not self._shutdown

    @property
    def supports_stop(self) -> bool:
        """Return whether configured STOP behavior is executable."""
        return self.config.stop_strategy is not StopStrategyType.UNSUPPORTED

    def async_add_update_callback(self, callback: UpdateCallback) -> Callable[[], None]:
        """Register a synchronous cached-state update callback."""
        self._callbacks.add(callback)

        def remove() -> None:
            self._callbacks.discard(callback)

        return remove

    async def async_initialize(self) -> None:
        """Cache source availability without executing a physical action."""
        available = await self._all_control_sources_available()
        self._apply_passive_event(
            GateEventType.SOURCE_AVAILABLE
            if available
            else GateEventType.SOURCE_UNAVAILABLE
        )

    async def async_open(self) -> None:
        """Request safe opening."""
        await self.async_command(GateCommand.OPEN)

    async def async_close(self) -> None:
        """Request safe closing."""
        await self.async_command(GateCommand.CLOSE)

    async def async_stop(self) -> None:
        """Request configured STOP behavior."""
        if not self.supports_stop:
            self._raise_rejected("stop_unsupported")
        await self.async_command(GateCommand.STOP)

    async def async_command(self, command: GateCommand) -> None:
        """Serialize a command and commit its state only after physical success."""
        async with self._command_lock:
            if self._shutdown:
                self._raise_rejected("controller_unloaded")

            available = await self._all_control_sources_available()
            self._apply_passive_event(
                GateEventType.SOURCE_AVAILABLE
                if available
                else GateEventType.SOURCE_UNAVAILABLE
            )
            if not available:
                self._raise_rejected("source_unavailable")
            if self._snapshot.problem is GateProblem.LIMIT_SENSOR_CONFLICT:
                self._raise_rejected("limit_sensor_conflict")
            if command is GateCommand.CLOSE and self._snapshot.obstacle_active:
                self._raise_rejected("obstacle_active")

            event_type = {
                GateCommand.OPEN: GateEventType.COMMAND_OPEN,
                GateCommand.CLOSE: GateEventType.COMMAND_CLOSE,
                GateCommand.STOP: GateEventType.COMMAND_STOP,
            }[command]
            original = self._snapshot
            transition = self._machine.transition(original, GateEvent(event_type))
            command_effects = tuple(
                effect
                for effect in transition.effects
                if effect.type
                in (
                    GateEffectType.EXECUTE_COMMAND,
                    GateEffectType.EXECUTE_STOP_STRATEGY,
                    GateEffectType.EXECUTE_DIRECTION_CHANGE_STRATEGY,
                    GateEffectType.EXECUTE_REPEATED_COMMAND_POLICY,
                )
            )
            if not command_effects:
                return

            sequence = self._sequence_for_effects(command_effects, original)
            task = asyncio.create_task(
                self._executor.async_execute(sequence),
                name=f"virtual_gate_{self.config.device_id}_{command.value}",
            )
            self._active_execution = task
            try:
                await task
            except SourceUnavailableError:
                self._apply_passive_event(GateEventType.SOURCE_UNAVAILABLE)
                self._raise_rejected("source_unavailable")
            finally:
                if self._active_execution is task:
                    self._active_execution = None

            # A failed or cancelled physical effect never leaks a logical transition.
            self._set_snapshot(transition.snapshot)

    async def async_shutdown(self) -> None:
        """Cancel and await owned work without initiating any new movement."""
        self._shutdown = True
        task = self._active_execution
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._callbacks.clear()

    async def _all_control_sources_available(self) -> bool:
        """Preflight every control required by this configured gate."""
        for source in self.config.control_sources:
            if not await self._actions.async_is_available(source):
                return False
        return True

    def _apply_passive_event(self, event_type: GateEventType) -> None:
        """Apply an event that cannot emit physical command effects."""
        transition = self._machine.transition(self._snapshot, GateEvent(event_type))
        if any(
            effect.type.value.startswith("execute") for effect in transition.effects
        ):
            msg = f"passive event unexpectedly emitted an action: {event_type.value}"
            raise RuntimeError(msg)
        self._set_snapshot(transition.snapshot)

    def _set_snapshot(self, snapshot: GateSnapshot) -> None:
        """Store and publish a changed immutable snapshot."""
        if snapshot == self._snapshot:
            return
        self._snapshot = snapshot
        for callback in tuple(self._callbacks):
            callback()

    def _sequence_for_effects(
        self, effects: tuple[GateEffect, ...], original: GateSnapshot
    ) -> CommandSequence:
        """Translate declarative effects into one executor-owned sequence."""
        steps: list[CommandStep] = []
        names: list[str] = []
        for effect in effects:
            names.append(effect.type.value)
            steps.extend(self._steps_for_effect(effect, original))
        if not steps:
            msg = "command effect produced an empty physical sequence"
            raise RuntimeError(msg)
        return CommandSequence(" + ".join(names), tuple(steps))

    def _steps_for_effect(
        self, effect: GateEffect, original: GateSnapshot
    ) -> tuple[CommandStep, ...]:
        """Build physical steps for one validated state-machine effect."""
        if effect.command is None:
            msg = "command effect is missing its command"
            raise RuntimeError(msg)
        if effect.type is GateEffectType.EXECUTE_COMMAND:
            return self._basic_command_steps(effect.command)
        if effect.type is GateEffectType.EXECUTE_STOP_STRATEGY:
            return self._stop_steps(original)
        if effect.type is GateEffectType.EXECUTE_DIRECTION_CHANGE_STRATEGY:
            return self._reversal_steps(effect.command, original)
        if (
            effect.type is GateEffectType.EXECUTE_REPEATED_COMMAND_POLICY
            and effect.strategy is RepeatedCommandPolicy.REPEAT
        ):
            return self._basic_command_steps(effect.command)
        msg = f"unsupported command effect: {effect.type.value}"
        raise RuntimeError(msg)

    def _basic_command_steps(self, command: GateCommand) -> tuple[CommandStep, ...]:
        source = self._source_for_command(command)
        return self._source_steps(source, self.config.pulse_duration_ms)

    def _stop_steps(self, snapshot: GateSnapshot) -> tuple[CommandStep, ...]:
        strategy = self.config.stop_strategy
        if strategy is StopStrategyType.DEDICATED:
            source = self.config.stop_source
            if source is None:
                raise RuntimeError("dedicated STOP has no source")
            return self._source_steps(source, self.config.pulse_duration_ms)

        same_direction = strategy in (
            StopStrategyType.PULSE_SAME_DIRECTION,
            StopStrategyType.HOLD_SAME_DIRECTION,
        )
        direction = snapshot.current_direction
        if direction is GateDirection.UNKNOWN:
            direction = snapshot.last_direction
        if direction is GateDirection.UNKNOWN:
            self._raise_rejected("direction_unknown")
        command = (
            GateCommand.OPEN
            if direction is GateDirection.OPENING
            else GateCommand.CLOSE
        )
        if not same_direction:
            command = (
                GateCommand.CLOSE if command is GateCommand.OPEN else GateCommand.OPEN
            )
        source = self._source_for_command(command)
        duration = (
            self.config.hold_duration_ms
            if strategy
            in (
                StopStrategyType.HOLD_SAME_DIRECTION,
                StopStrategyType.HOLD_OPPOSITE_DIRECTION,
            )
            else self.config.pulse_duration_ms
        )
        return self._source_steps(source, duration)

    def _reversal_steps(
        self, command: GateCommand, snapshot: GateSnapshot
    ) -> tuple[CommandStep, ...]:
        strategy = self.config.direction_change_strategy
        if strategy is DirectionChangeStrategyType.DIRECT:
            return self._basic_command_steps(command)
        if strategy in (
            DirectionChangeStrategyType.STOP_THEN_REVERSE,
            DirectionChangeStrategyType.STOP_WAIT_REVERSE,
        ):
            steps = list(self._stop_steps(snapshot))
            if (
                strategy is DirectionChangeStrategyType.STOP_WAIT_REVERSE
                and self.config.direction_change_delay_ms > 0
            ):
                steps.append(
                    CommandStep(
                        CommandStepType.DELAY,
                        duration_ms=self.config.direction_change_delay_ms,
                    )
                )
            steps.extend(self._basic_command_steps(command))
            return tuple(steps)
        if strategy is DirectionChangeStrategyType.MULTI_PULSE:
            pulse = self._basic_command_steps(command)
            multi_steps: list[CommandStep] = []
            for index in range(self.config.pulse_count):
                if index and self.config.pulse_interval_ms > 0:
                    multi_steps.append(
                        CommandStep(
                            CommandStepType.DELAY,
                            duration_ms=self.config.pulse_interval_ms,
                        )
                    )
                multi_steps.extend(pulse)
            return tuple(multi_steps)
        msg = f"unsupported reversal strategy: {strategy.value}"
        raise RuntimeError(msg)

    def _source_for_command(self, command: GateCommand) -> SourceRef:
        if command is GateCommand.STOP:
            source = self.config.stop_source
        elif self.config.step_source is not None:
            source = self.config.step_source
        elif command is GateCommand.OPEN:
            source = self.config.open_source
        else:
            source = self.config.close_source
        if source is None:
            msg = f"no configured source for {command.value}"
            raise RuntimeError(msg)
        return source

    @staticmethod
    def _source_steps(source: SourceRef, duration_ms: int) -> tuple[CommandStep, ...]:
        if source.action_type is ControlActionType.BUTTON:
            return (CommandStep(CommandStepType.PRESS, source=source),)
        return (
            CommandStep(CommandStepType.ACTIVATE, source=source),
            CommandStep(CommandStepType.DELAY, duration_ms=duration_ms),
            CommandStep(CommandStepType.DEACTIVATE, source=source),
        )

    @staticmethod
    def _raise_rejected(key: str) -> None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=key,
        )
