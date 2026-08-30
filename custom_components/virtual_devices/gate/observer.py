"""Event-driven Home Assistant source observation for Virtual Gate."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .models import GateEvent, GateEventType
from .state_machine import GateEndpoint

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from homeassistant.core import HomeAssistant, State

    from .config import GateConfig, GateLimitConfig
    from .controller import GateController


class GateSourceObserver:
    """Observe configured controls and sensors without polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: GateConfig,
        controller: GateController,
    ) -> None:
        """Bind one observer to one entry-owned controller."""
        self._hass = hass
        self._config = config
        self._controller = controller
        self._unsubscribe: Callable[[], None] | None = None
        self._pending_debounce: dict[str, Callable[[], None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._stopped = False
        self._initializing = True

    async def async_start(self) -> None:
        """Register listeners, debounce initial limits, and cache source state."""
        entity_ids = self._observed_entity_ids()
        if entity_ids:
            self._unsubscribe = async_track_state_change_event(
                self._hass,
                entity_ids,
                self._async_state_changed,
            )

        maximum_debounce_ms = max(
            (
                limit.debounce_ms
                for limit in (self._config.open_limit, self._config.closed_limit)
                if limit is not None
            ),
            default=0,
        )
        if maximum_debounce_ms:
            await asyncio.sleep(maximum_debounce_ms / 1000)

        source_available = all(
            self._usable(self._hass.states.get(source.entity_id))
            for source in self._config.control_sources
        )
        sensor_ids = self._sensor_entity_ids()
        sensor_available = all(
            self._usable(self._hass.states.get(entity_id)) for entity_id in sensor_ids
        )
        await self._controller.async_initialize_observations(
            open_limit_active=self._initial_limit_active(self._config.open_limit),
            closed_limit_active=self._initial_limit_active(self._config.closed_limit),
            source_available=source_available,
            sensor_available=sensor_available,
            obstacle_active=self._initial_obstacle_active(),
        )
        self._initializing = False

    async def async_shutdown(self) -> None:
        """Remove listeners, debounce callbacks, and owned event tasks."""
        self._stopped = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        for cancel in self._pending_debounce.values():
            cancel()
        self._pending_debounce.clear()
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Schedule async handling from the event-loop callback."""
        if self._stopped or self._initializing:
            return
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        if entity_id in {source.entity_id for source in self._config.control_sources}:
            self._create_task(self._async_refresh_control_availability())
            return
        if self._config.open_limit is not None and (
            entity_id == self._config.open_limit.entity_id
        ):
            self._schedule_limit_debounce(
                GateEndpoint.OPEN, self._config.open_limit, new_state
            )
        elif self._config.closed_limit is not None and (
            entity_id == self._config.closed_limit.entity_id
        ):
            self._schedule_limit_debounce(
                GateEndpoint.CLOSED, self._config.closed_limit, new_state
            )
        elif entity_id == self._config.obstacle_source:
            self._create_task(self._async_apply_obstacle())
        self._refresh_sensor_availability()

    def _schedule_limit_debounce(
        self,
        endpoint: GateEndpoint,
        limit: GateLimitConfig,
        new_state: State | None,
    ) -> None:
        """Accept a limit only after its raw state remains stable."""
        existing = self._pending_debounce.pop(limit.entity_id, None)
        if existing is not None:
            existing()
        if new_state is None or not self._usable(new_state):
            return
        expected = new_state.state
        if limit.debounce_ms == 0:
            self._create_task(self._async_apply_limit(endpoint, limit, expected))
            return

        async def apply_after_debounce(now: Any) -> None:
            del now
            self._pending_debounce.pop(limit.entity_id, None)
            await self._async_apply_limit(endpoint, limit, expected)

        self._pending_debounce[limit.entity_id] = async_call_later(
            self._hass,
            limit.debounce_ms / 1000,
            apply_after_debounce,
        )

    async def _async_apply_limit(
        self, endpoint: GateEndpoint, limit: GateLimitConfig, expected: str
    ) -> None:
        """Verify stable raw state and emit its normalized endpoint event."""
        if self._stopped:
            return
        current = self._hass.states.get(limit.entity_id)
        if current is None or not self._usable(current):
            return
        if current.state != expected:
            return
        await self._controller.async_handle_limit(
            endpoint, raw_is_on=current.state == STATE_ON
        )

    async def _async_apply_obstacle(self) -> None:
        if self._config.obstacle_source is None or self._stopped:
            return
        state = self._hass.states.get(self._config.obstacle_source)
        if state is None or not self._usable(state):
            return
        event_type = (
            GateEventType.OBSTACLE_ON
            if state.state == STATE_ON
            else GateEventType.OBSTACLE_OFF
        )
        await self._controller.async_handle_event(GateEvent(event_type))

    async def _async_refresh_control_availability(self) -> None:
        if self._stopped:
            return
        available = all(
            self._usable(self._hass.states.get(source.entity_id))
            for source in self._config.control_sources
        )
        event_type = (
            GateEventType.SOURCE_AVAILABLE
            if available
            else GateEventType.SOURCE_UNAVAILABLE
        )
        await self._controller.async_handle_event(GateEvent(event_type))

    def _refresh_sensor_availability(self) -> None:
        sensor_ids = self._sensor_entity_ids()
        available = all(
            self._usable(self._hass.states.get(entity_id)) for entity_id in sensor_ids
        )
        self._controller.set_sensor_available(available)

    def _sensor_entity_ids(self) -> list[str]:
        sensor_ids = [
            limit.entity_id
            for limit in (self._config.open_limit, self._config.closed_limit)
            if limit is not None
        ]
        if self._config.obstacle_source is not None:
            sensor_ids.append(self._config.obstacle_source)
        return sensor_ids

    def _initial_limit_active(self, limit: GateLimitConfig | None) -> bool:
        if limit is None:
            return False
        state = self._hass.states.get(limit.entity_id)
        if not self._usable(state) or state is None:
            return False
        return (state.state == STATE_ON) is limit.active_state

    def _initial_obstacle_active(self) -> bool:
        if self._config.obstacle_source is None:
            return False
        state = self._hass.states.get(self._config.obstacle_source)
        return self._usable(state) and state is not None and state.state == STATE_ON

    def _observed_entity_ids(self) -> list[str]:
        entity_ids = [source.entity_id for source in self._config.control_sources]
        entity_ids.extend(
            limit.entity_id
            for limit in (self._config.open_limit, self._config.closed_limit)
            if limit is not None
        )
        if self._config.obstacle_source is not None:
            entity_ids.append(self._config.obstacle_source)
        return entity_ids

    def _create_task(self, coro: Coroutine[Any, Any, None]) -> None:
        task = self._hass.async_create_task(
            coro,
            f"virtual_gate_observer_{self._config.device_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @staticmethod
    def _usable(state: State | None) -> bool:
        return state is not None and state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )
