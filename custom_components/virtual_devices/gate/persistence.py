"""Restart-safe semantic persistence for Virtual Gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Self

from homeassistant.helpers.storage import Store

from .models import (
    GateCommand,
    GateDirection,
    GateProblem,
    GateSnapshot,
    GateState,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

STORAGE_VERSION = 1


@dataclass(frozen=True, slots=True)
class GateStoredState:
    """Safe semantic context that can never encode an executable action."""

    state: GateState
    last_direction: GateDirection
    estimated_position: float | None
    last_command: GateCommand | None
    last_transition_timestamp: str

    @classmethod
    def from_snapshot(cls, snapshot: GateSnapshot) -> Self:
        """Capture only semantic fields; timers and command sequences are omitted."""
        return cls(
            state=snapshot.state,
            last_direction=snapshot.last_direction,
            estimated_position=snapshot.estimated_position,
            last_command=snapshot.last_command,
            last_transition_timestamp=datetime.now(UTC).isoformat(),
        )

    def to_snapshot(self) -> GateSnapshot:
        """Return passive restored context for state-machine reconciliation."""
        direction = GateDirection.UNKNOWN
        if self.state is GateState.OPENING:
            direction = GateDirection.OPENING
        elif self.state is GateState.CLOSING:
            direction = GateDirection.CLOSING
        return GateSnapshot(
            state=self.state,
            current_direction=direction,
            last_direction=self.last_direction,
            estimated_position=self.estimated_position,
            problem=GateProblem.NONE,
            last_command=self.last_command,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to Home Assistant storage-safe primitives."""
        return {
            "state": self.state.value,
            "last_direction": self.last_direction.value,
            "estimated_position": self.estimated_position,
            "last_command": self.last_command.value
            if self.last_command is not None
            else None,
            "last_transition_timestamp": self.last_transition_timestamp,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Validate and deserialize persisted semantic context."""
        raw_command = value.get("last_command")
        raw_position = value.get("estimated_position")
        return cls(
            state=GateState(value["state"]),
            last_direction=GateDirection(value["last_direction"]),
            estimated_position=float(raw_position)
            if raw_position is not None
            else None,
            last_command=GateCommand(raw_command) if raw_command is not None else None,
            last_transition_timestamp=str(value["last_transition_timestamp"]),
        )


class GatePersistence:
    """Store one gate's semantic state under its stable config-entry identity."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create a private versioned HA storage helper."""
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"virtual_devices.{entry_id}",
            private=True,
        )
        self._latest: GateStoredState | None = None

    async def async_load(self) -> GateSnapshot | None:
        """Load semantic context without starting movement or timers."""
        raw = await self._store.async_load()
        if raw is None:
            return None
        stored = GateStoredState.from_dict(raw)
        self._latest = stored
        return stored.to_snapshot()

    def schedule_save(self, snapshot: GateSnapshot) -> None:
        """Debounce persistence writes while retaining the newest snapshot."""
        self._latest = GateStoredState.from_snapshot(snapshot)
        self._store.async_delay_save(self._serialize_latest, delay=1)

    async def async_flush(self, snapshot: GateSnapshot) -> None:
        """Persist the final safe snapshot before unload completes."""
        self._latest = GateStoredState.from_snapshot(snapshot)
        await self._store.async_save(self._serialize_latest())

    def _serialize_latest(self) -> dict[str, Any]:
        if self._latest is None:
            raise RuntimeError("no gate state is available to persist")
        return self._latest.to_dict()
