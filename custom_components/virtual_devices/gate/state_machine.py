"""Deterministic, side-effect-free state machine for Virtual Gate."""

from dataclasses import dataclass, replace
from enum import StrEnum

from .models import (
    DirectionChangeStrategyType,
    GateCommand,
    GateDirection,
    GateEffect,
    GateEffectType,
    GateEvent,
    GateEventType,
    GateProblem,
    GateSnapshot,
    GateState,
    GateTransition,
    RepeatedCommandPolicy,
    StopStrategyType,
)


class GateEndpoint(StrEnum):
    """Physical endpoint represented by a configured limit sensor."""

    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class LimitSensorConfig:
    """State-machine-facing endpoint sensor configuration."""

    active_state: bool = True


@dataclass(frozen=True, slots=True)
class GateStateMachineConfig:
    """Behavior required to decide deterministic state transitions."""

    open_limit: LimitSensorConfig | None = None
    closed_limit: LimitSensorConfig | None = None
    stop_strategy: StopStrategyType = StopStrategyType.UNSUPPORTED
    direction_change_strategy: DirectionChangeStrategyType = (
        DirectionChangeStrategyType.UNSUPPORTED
    )
    repeated_open_policy: RepeatedCommandPolicy = RepeatedCommandPolicy.IGNORE
    repeated_close_policy: RepeatedCommandPolicy = RepeatedCommandPolicy.IGNORE


class GateStateMachine:
    """Apply events to immutable snapshots and emit declarative effects."""

    def __init__(self, config: GateStateMachineConfig) -> None:
        """Initialize the state machine with immutable behavior configuration."""
        self._config = config

    def limit_event(self, endpoint: GateEndpoint, *, raw_is_on: bool) -> GateEvent:
        """Normalize a raw sensor value using configured active-state inversion."""
        sensor = (
            self._config.open_limit
            if endpoint is GateEndpoint.OPEN
            else self._config.closed_limit
        )
        if sensor is None:
            msg = f"{endpoint.value} limit is not configured"
            raise ValueError(msg)

        active = raw_is_on is sensor.active_state
        event_type = {
            (GateEndpoint.OPEN, True): GateEventType.OPEN_LIMIT_ON,
            (GateEndpoint.OPEN, False): GateEventType.OPEN_LIMIT_OFF,
            (GateEndpoint.CLOSED, True): GateEventType.CLOSED_LIMIT_ON,
            (GateEndpoint.CLOSED, False): GateEventType.CLOSED_LIMIT_OFF,
        }[(endpoint, active)]
        return GateEvent(event_type)

    def transition(self, snapshot: GateSnapshot, event: GateEvent) -> GateTransition:
        """Return the next immutable snapshot and requested side effects."""
        if event.type is GateEventType.COMMAND_OPEN:
            return self._command(snapshot, GateCommand.OPEN)
        if event.type is GateEventType.COMMAND_CLOSE:
            return self._command(snapshot, GateCommand.CLOSE)
        if event.type is GateEventType.COMMAND_STOP:
            return self._stop(snapshot)
        if event.type in (
            GateEventType.OPEN_LIMIT_ON,
            GateEventType.OPEN_LIMIT_OFF,
            GateEventType.CLOSED_LIMIT_ON,
            GateEventType.CLOSED_LIMIT_OFF,
        ):
            return self._limit(snapshot, event.type)
        if event.type is GateEventType.MOVEMENT_TIMEOUT:
            return self._timeout(snapshot)
        if event.type is GateEventType.SOURCE_UNAVAILABLE:
            return self._source_availability(snapshot, available=False)
        if event.type is GateEventType.SOURCE_AVAILABLE:
            return self._source_availability(snapshot, available=True)
        if event.type is GateEventType.OBSTACLE_ON:
            return self._obstacle(snapshot, active=True)
        if event.type is GateEventType.OBSTACLE_OFF:
            return self._obstacle(snapshot, active=False)
        if event.type is GateEventType.RESTORE:
            return self._restore(snapshot)
        return GateTransition(snapshot)

    def _command(self, snapshot: GateSnapshot, command: GateCommand) -> GateTransition:
        """Handle an OPEN or CLOSE request."""
        if self._commands_blocked(snapshot, command):
            return GateTransition(snapshot)

        target_state = (
            GateState.OPENING if command is GateCommand.OPEN else GateState.CLOSING
        )
        target_direction = (
            GateDirection.OPENING
            if command is GateCommand.OPEN
            else GateDirection.CLOSING
        )
        same_direction_state = target_state
        target_endpoint_state = (
            GateState.OPEN if command is GateCommand.OPEN else GateState.CLOSED
        )
        opposite_state = (
            GateState.CLOSING if command is GateCommand.OPEN else GateState.OPENING
        )

        if snapshot.state in (same_direction_state, target_endpoint_state):
            return self._repeated_command(snapshot, command)
        if snapshot.state is opposite_state:
            return self._reverse(snapshot, command, target_state, target_direction)
        if snapshot.state is GateState.UNKNOWN_MOVING:
            return GateTransition(snapshot)

        start_position = snapshot.estimated_position
        if snapshot.state is GateState.CLOSED:
            start_position = 0
        elif snapshot.state is GateState.OPEN:
            start_position = 100

        next_snapshot = replace(
            snapshot,
            state=target_state,
            current_direction=target_direction,
            last_direction=target_direction,
            estimated_position=start_position,
            problem=self._ambient_problem(snapshot),
            last_command=command,
        )
        return self._result(
            snapshot,
            next_snapshot,
            (
                GateEffect(GateEffectType.EXECUTE_COMMAND, command),
                GateEffect(GateEffectType.START_MOVEMENT_TIMER),
            ),
        )

    def _commands_blocked(self, snapshot: GateSnapshot, command: GateCommand) -> bool:
        """Return whether safety/runtime state rejects a movement request."""
        if snapshot.problem is GateProblem.LIMIT_SENSOR_CONFLICT:
            return True
        if not snapshot.source_available:
            return True
        return command is GateCommand.CLOSE and snapshot.obstacle_active

    def _repeated_command(
        self, snapshot: GateSnapshot, command: GateCommand
    ) -> GateTransition:
        """Apply the configured policy for a redundant command."""
        policy = (
            self._config.repeated_open_policy
            if command is GateCommand.OPEN
            else self._config.repeated_close_policy
        )
        if policy is RepeatedCommandPolicy.IGNORE:
            return GateTransition(snapshot)
        if policy is RepeatedCommandPolicy.STOP:
            if snapshot.state in (GateState.OPENING, GateState.CLOSING):
                return self._stop(snapshot)
            return GateTransition(snapshot)

        next_snapshot = replace(snapshot, last_command=command)
        return self._result(
            snapshot,
            next_snapshot,
            (
                GateEffect(
                    GateEffectType.EXECUTE_REPEATED_COMMAND_POLICY,
                    command,
                    policy,
                ),
            ),
        )

    def _reverse(
        self,
        snapshot: GateSnapshot,
        command: GateCommand,
        target_state: GateState,
        target_direction: GateDirection,
    ) -> GateTransition:
        """Apply an explicit direction-change strategy."""
        strategy = self._config.direction_change_strategy
        if strategy is DirectionChangeStrategyType.UNSUPPORTED:
            return GateTransition(snapshot)

        next_snapshot = replace(
            snapshot,
            state=target_state,
            current_direction=target_direction,
            last_direction=target_direction,
            problem=self._ambient_problem(snapshot),
            last_command=command,
        )
        return self._result(
            snapshot,
            next_snapshot,
            (
                GateEffect(
                    GateEffectType.EXECUTE_DIRECTION_CHANGE_STRATEGY,
                    command,
                    strategy,
                ),
                GateEffect(GateEffectType.CANCEL_MOVEMENT_TIMER),
                GateEffect(GateEffectType.START_MOVEMENT_TIMER),
            ),
        )

    def _stop(self, snapshot: GateSnapshot) -> GateTransition:
        """Stop motion through the configured strategy while preserving history."""
        if snapshot.state not in (
            GateState.OPENING,
            GateState.CLOSING,
            GateState.UNKNOWN_MOVING,
        ):
            return GateTransition(snapshot)
        strategy = self._config.stop_strategy
        if strategy is StopStrategyType.UNSUPPORTED or not snapshot.source_available:
            return GateTransition(snapshot)

        last_direction = snapshot.last_direction
        if snapshot.current_direction is not GateDirection.UNKNOWN:
            last_direction = snapshot.current_direction
        next_snapshot = replace(
            snapshot,
            state=GateState.STOPPED,
            current_direction=GateDirection.UNKNOWN,
            last_direction=last_direction,
            problem=self._ambient_problem(snapshot),
            last_command=GateCommand.STOP,
        )
        return self._result(
            snapshot,
            next_snapshot,
            (
                GateEffect(
                    GateEffectType.EXECUTE_STOP_STRATEGY,
                    GateCommand.STOP,
                    strategy,
                ),
                GateEffect(GateEffectType.CANCEL_MOVEMENT_TIMER),
            ),
        )

    def _limit(
        self, snapshot: GateSnapshot, event_type: GateEventType
    ) -> GateTransition:
        """Apply a semantic endpoint sensor event with physical precedence."""
        is_open_limit = event_type in (
            GateEventType.OPEN_LIMIT_ON,
            GateEventType.OPEN_LIMIT_OFF,
        )
        if is_open_limit and self._config.open_limit is None:
            return GateTransition(snapshot)
        if not is_open_limit and self._config.closed_limit is None:
            return GateTransition(snapshot)

        active = event_type in (
            GateEventType.OPEN_LIMIT_ON,
            GateEventType.CLOSED_LIMIT_ON,
        )
        changed = replace(
            snapshot,
            open_limit_active=active if is_open_limit else snapshot.open_limit_active,
            closed_limit_active=active
            if not is_open_limit
            else snapshot.closed_limit_active,
        )

        if changed.open_limit_active and changed.closed_limit_active:
            conflict = replace(
                changed,
                state=GateState.ERROR,
                current_direction=GateDirection.UNKNOWN,
                problem=GateProblem.LIMIT_SENSOR_CONFLICT,
            )
            effects = self._cancel_timer_if_moving(snapshot)
            return self._result(snapshot, conflict, effects)

        if active:
            endpoint_state = GateState.OPEN if is_open_limit else GateState.CLOSED
            endpoint_position = 100 if is_open_limit else 0
            endpoint = replace(
                changed,
                state=endpoint_state,
                current_direction=GateDirection.UNKNOWN,
                estimated_position=endpoint_position,
                problem=self._ambient_problem(changed),
            )
            effects = self._cancel_timer_if_moving(snapshot)
            return self._result(snapshot, endpoint, effects)

        if snapshot.problem is GateProblem.LIMIT_SENSOR_CONFLICT:
            resolved_position: float | None
            if changed.open_limit_active:
                resolved_state = GateState.OPEN
                resolved_position = 100
            elif changed.closed_limit_active:
                resolved_state = GateState.CLOSED
                resolved_position = 0
            else:
                resolved_state = GateState.UNKNOWN
                resolved_position = changed.estimated_position
            resolved = replace(
                changed,
                state=resolved_state,
                current_direction=GateDirection.UNKNOWN,
                estimated_position=resolved_position,
                problem=self._ambient_problem(changed),
            )
            return self._result(snapshot, resolved)

        if is_open_limit and snapshot.state is GateState.OPEN:
            return self._external_motion(snapshot, changed, GateDirection.CLOSING)
        if not is_open_limit and snapshot.state is GateState.CLOSED:
            return self._external_motion(snapshot, changed, GateDirection.OPENING)
        return self._result(snapshot, changed)

    def _external_motion(
        self,
        original: GateSnapshot,
        changed: GateSnapshot,
        direction: GateDirection,
    ) -> GateTransition:
        """Infer direction from a physical endpoint becoming inactive."""
        state = (
            GateState.OPENING
            if direction is GateDirection.OPENING
            else GateState.CLOSING
        )
        moving = replace(
            changed,
            state=state,
            current_direction=direction,
            last_direction=direction,
            problem=self._ambient_problem(changed),
        )
        return self._result(
            original,
            moving,
            (GateEffect(GateEffectType.START_MOVEMENT_TIMER),),
        )

    def _timeout(self, snapshot: GateSnapshot) -> GateTransition:
        """Resolve travel timeout according to endpoint sensor authority."""
        if snapshot.state is GateState.OPENING:
            if self._config.open_limit is not None:
                timed_out = replace(
                    snapshot,
                    state=GateState.ERROR,
                    current_direction=GateDirection.UNKNOWN,
                    problem=GateProblem.OPENING_TIMEOUT,
                )
            else:
                timed_out = replace(
                    snapshot,
                    state=GateState.OPEN,
                    current_direction=GateDirection.UNKNOWN,
                    estimated_position=100,
                    problem=self._ambient_problem(snapshot),
                )
        elif snapshot.state is GateState.CLOSING:
            if self._config.closed_limit is not None:
                timed_out = replace(
                    snapshot,
                    state=GateState.ERROR,
                    current_direction=GateDirection.UNKNOWN,
                    problem=GateProblem.CLOSING_TIMEOUT,
                )
            else:
                timed_out = replace(
                    snapshot,
                    state=GateState.CLOSED,
                    current_direction=GateDirection.UNKNOWN,
                    estimated_position=0,
                    problem=self._ambient_problem(snapshot),
                )
        else:
            return GateTransition(snapshot)

        return self._result(
            snapshot,
            timed_out,
            (GateEffect(GateEffectType.CANCEL_MOVEMENT_TIMER),),
        )

    def _source_availability(
        self, snapshot: GateSnapshot, *, available: bool
    ) -> GateTransition:
        """Track command-source availability separately from logical state."""
        changed = replace(snapshot, source_available=available)
        problem = self._ambient_problem(changed)
        if available and snapshot.problem not in (
            GateProblem.NONE,
            GateProblem.SOURCE_UNAVAILABLE,
        ):
            problem = snapshot.problem
        return self._result(snapshot, replace(changed, problem=problem))

    def _obstacle(self, snapshot: GateSnapshot, *, active: bool) -> GateTransition:
        """Track a configured safety input without initiating movement."""
        changed = replace(snapshot, obstacle_active=active)
        problem = self._ambient_problem(changed)
        if not active and snapshot.problem not in (
            GateProblem.NONE,
            GateProblem.OBSTACLE,
        ):
            problem = snapshot.problem
        return self._result(snapshot, replace(changed, problem=problem))

    def _restore(self, snapshot: GateSnapshot) -> GateTransition:
        """Reconcile restored context without emitting physical commands."""
        if snapshot.open_limit_active and snapshot.closed_limit_active:
            restored = replace(
                snapshot,
                state=GateState.ERROR,
                current_direction=GateDirection.UNKNOWN,
                problem=GateProblem.LIMIT_SENSOR_CONFLICT,
            )
            return self._result(snapshot, restored)
        if snapshot.closed_limit_active:
            restored = replace(
                snapshot,
                state=GateState.CLOSED,
                current_direction=GateDirection.UNKNOWN,
                estimated_position=0,
                problem=self._ambient_problem(snapshot),
            )
            return self._result(snapshot, restored)
        if snapshot.open_limit_active:
            restored = replace(
                snapshot,
                state=GateState.OPEN,
                current_direction=GateDirection.UNKNOWN,
                estimated_position=100,
                problem=self._ambient_problem(snapshot),
            )
            return self._result(snapshot, restored)

        if snapshot.state in (
            GateState.OPENING,
            GateState.CLOSING,
            GateState.UNKNOWN_MOVING,
            GateState.STOPPED,
        ):
            restored_state = GateState.STOPPED
        elif snapshot.state is GateState.CLOSED and self._config.closed_limit is None:
            restored_state = GateState.CLOSED
        elif snapshot.state is GateState.OPEN and self._config.open_limit is None:
            restored_state = GateState.OPEN
        else:
            restored_state = GateState.UNKNOWN

        restored = replace(
            snapshot,
            state=restored_state,
            current_direction=GateDirection.UNKNOWN,
            problem=self._ambient_problem(snapshot),
        )
        return self._result(snapshot, restored)

    @staticmethod
    def _cancel_timer_if_moving(
        snapshot: GateSnapshot,
    ) -> tuple[GateEffect, ...]:
        """Request timer cancellation only when movement may own a timer."""
        if snapshot.state in (GateState.OPENING, GateState.CLOSING):
            return (GateEffect(GateEffectType.CANCEL_MOVEMENT_TIMER),)
        return ()

    @staticmethod
    def _ambient_problem(snapshot: GateSnapshot) -> GateProblem:
        """Return the highest-priority current non-timeout problem."""
        if snapshot.open_limit_active and snapshot.closed_limit_active:
            return GateProblem.LIMIT_SENSOR_CONFLICT
        if not snapshot.source_available:
            return GateProblem.SOURCE_UNAVAILABLE
        if snapshot.obstacle_active:
            return GateProblem.OBSTACLE
        return GateProblem.NONE

    @staticmethod
    def _result(
        original: GateSnapshot,
        next_snapshot: GateSnapshot,
        effects: tuple[GateEffect, ...] = (),
    ) -> GateTransition:
        """Append a state notification only when semantic state changed."""
        if next_snapshot != original:
            effects = (*effects, GateEffect(GateEffectType.STATE_CHANGED))
        return GateTransition(next_snapshot, effects)
