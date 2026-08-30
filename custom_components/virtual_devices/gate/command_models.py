"""Serializable physical command sequence models."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from .models import ControlActionType


class CommandStepType(StrEnum):
    """Atomic command step understood by the future executor."""

    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    PRESS = "press"
    DELAY = "delay"


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Reference to a configured Home Assistant source entity."""

    entity_id: str
    action_type: ControlActionType

    def __post_init__(self) -> None:
        """Validate source identity without importing Home Assistant."""
        if not self.entity_id or "." not in self.entity_id:
            msg = "entity_id must contain a Home Assistant domain and object ID"
            raise ValueError(msg)

        domain, object_id = self.entity_id.split(".", maxsplit=1)
        if not domain or not object_id:
            msg = "entity_id must contain a Home Assistant domain and object ID"
            raise ValueError(msg)

        expected_domain = self.action_type.value
        if domain != expected_domain:
            msg = f"{self.action_type.value} source requires {expected_domain} domain"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, str]:
        """Return a storage-safe representation."""
        return {
            "entity_id": self.entity_id,
            "action_type": self.action_type.value,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Restore a source reference from storage-safe data."""
        return cls(
            entity_id=str(value["entity_id"]),
            action_type=ControlActionType(value["action_type"]),
        )


@dataclass(frozen=True, slots=True)
class CommandStep:
    """One validated, serializable physical command step."""

    type: CommandStepType
    source: SourceRef | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        """Validate the payload required by the selected step type."""
        if self.type is CommandStepType.DELAY:
            if self.source is not None or self.duration_ms is None:
                msg = "delay requires duration_ms and no source"
                raise ValueError(msg)
            if self.duration_ms <= 0:
                msg = "duration_ms must be positive"
                raise ValueError(msg)
            return

        if self.source is None or self.duration_ms is not None:
            msg = "source steps require a source and no duration_ms"
            raise ValueError(msg)

        if self.type in (CommandStepType.ACTIVATE, CommandStepType.DEACTIVATE):
            if self.source.action_type is not ControlActionType.SWITCH:
                msg = "activate/deactivate steps require a switch source"
                raise ValueError(msg)
        elif (
            self.type is CommandStepType.PRESS
            and self.source.action_type is not ControlActionType.BUTTON
        ):
            msg = "press step requires a button source"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Return a storage-safe representation."""
        value: dict[str, Any] = {"type": self.type.value}
        if self.source is not None:
            value["source"] = self.source.to_dict()
        if self.duration_ms is not None:
            value["duration_ms"] = self.duration_ms
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Restore and validate one command step."""
        raw_source = value.get("source")
        return cls(
            type=CommandStepType(value["type"]),
            source=SourceRef.from_dict(raw_source)
            if isinstance(raw_source, dict)
            else None,
            duration_ms=value.get("duration_ms"),
        )


@dataclass(frozen=True, slots=True)
class CommandSequence:
    """Named non-empty sequence of physical command steps."""

    name: str
    steps: tuple[CommandStep, ...]

    def __post_init__(self) -> None:
        """Reject unnamed or empty command sequences."""
        if not self.name.strip():
            msg = "command sequence requires a name"
            raise ValueError(msg)
        if not self.steps:
            msg = "command sequence requires at least one step"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Return a storage-safe representation."""
        return {
            "name": self.name,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        """Restore and validate a command sequence."""
        raw_steps = value["steps"]
        if not isinstance(raw_steps, list):
            msg = "steps must be a list"
            raise TypeError(msg)
        return cls(
            name=str(value["name"]),
            steps=tuple(CommandStep.from_dict(step) for step in raw_steps),
        )
