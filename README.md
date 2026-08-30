# Virtual Devices for Home Assistant

Virtual Devices is a Home Assistant custom integration that combines existing
entities into higher-level devices. The MVP provides **Virtual Gate**: one native
gate cover backed by existing switch/button controls and optional binary sensors.

The integration runs entirely inside Home Assistant. It has no external service,
custom frontend, or direct vendor-hardware connection.

> [!WARNING]
> This is pre-release software for a physical access device. Automated simulated
> tests have been completed, but a controlled hardware test is still required before
> release. Keep certified hardware safety systems in place and test with the motor
> disconnected first.

## Requirements

- Home Assistant 2026.8.0 or newer
- HACS 2.x for the intended installation path
- Existing `switch` or `button` entities that operate the physical controller
- Optional `binary_sensor` entities for endpoints and obstacle indication

## Installation

The repository must be public before HACS can validate or install it as a custom
repository. Once a public release is available:

1. Open HACS in Home Assistant.
2. Add this GitHub repository as a custom repository in the **Integration** category.
3. Install **Virtual Devices** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration**.
5. Search for **Virtual Devices**.

For development, copy `custom_components/virtual_devices` into the Home Assistant
configuration directory and restart Home Assistant.

## Creating a Virtual Gate

The native setup flow collects five groups of required configuration:

1. Gate name and controller mode.
2. Existing control entities.
3. Optional endpoint and obstacle sensors.
4. Independent opening/closing travel times and timeout margins.
5. Pulse, HOLD, STOP, reversal, and repeated-command behavior.

Each gate is one independent config entry and one Home Assistant device. Multiple
gates can coexist without sharing listeners, timers, state, or command queues.

### Controller modes

- **Single step-by-step** — one control cycles through behavior provided by the
  physical controller. Configure STOP/reversal only when its sequence is known.
- **Separate OPEN/CLOSE** — distinct direction controls and no dedicated STOP input.
- **Separate OPEN/CLOSE/STOP** — distinct direction and STOP controls.

`switch` sources are activated for the configured pulse/HOLD duration and always
deactivated in cleanup. `button` sources use the native press action. OPEN and CLOSE
outputs are interlocked and physical sequences are serialized.

## Endpoint and obstacle sensors

You can configure zero, one, or two endpoint sensors. Each endpoint has its own:

- binary sensor entity;
- active-state polarity (normal or inverted);
- debounce duration.

Physical endpoints outrank estimates and restored history. If both endpoints are
active, the gate reports `LIMIT_SENSOR_CONFLICT` and blocks movement. It never moves
automatically to resolve a conflict.

An optional obstacle sensor blocks CLOSE while active. Software obstacle handling is
diagnostic convenience, not a replacement for certified photocells, edge sensors,
or controller safety logic.

## Timing and estimated position

Opening and closing use independent travel times and margins. Position is estimated
from 0 (closed) to 100 (open), freezes after STOP, and recalibrates at a physical
endpoint.

- With the relevant endpoint sensor, travel time plus margin without activation
  produces an opening/closing timeout fault. The integration does not fabricate the
  endpoint.
- Without that endpoint sensor, elapsed travel time can establish OPEN or CLOSED.

Estimated position is informational. `SET_POSITION` is intentionally not supported
in the MVP.

## STOP, reversal, and repeated commands

STOP is advertised by the cover only when a configured strategy is executable.
Available strategies include a dedicated input, same/opposite-direction pulse, and
same/opposite-direction bounded HOLD.

Direction reversal can be direct, stop-then-reverse, stop-wait-reverse, or
multi-pulse when compatible with the selected controller. Redundant OPEN/CLOSE
commands default to **Ignore**; optional Repeat and Stop policies must match the
physical controller.

Incorrect strategy selection can cause unexpected physical behavior. Confirm the
controller manual and test each sequence with the motor disconnected.

## External movement and restart behavior

Endpoint changes can infer externally initiated movement, for example when a remote
opens a gate from CLOSED. When direction cannot be supported by evidence, the domain
keeps an unknown state instead of guessing.

Persistence stores semantic context only: state, last direction, position estimate,
last command, and timestamp. Startup/reload reads debounced physical sensors before
one passive restore. It never resumes a saved movement, pulse, HOLD, or timer.

## Home Assistant entities

Every gate provides:

- `cover.<gate>` — OPEN/CLOSE and dynamically available STOP;
- `sensor.<gate>_detailed_state` — enabled diagnostic enum;
- `sensor.<gate>_last_direction` — disabled by default;
- `sensor.<gate>_last_command` — disabled by default;
- `binary_sensor.<gate>_problem` — active when a detailed problem exists.

Config-entry diagnostics include redacted configuration and runtime state. Gate
names, stable IDs, and source entity IDs are not included.

## Reconfiguration

Use **Settings → Devices & services → Virtual Devices → Configure** to change all
required setup data. Reconfiguration unloads the old listener/timer/controller set,
updates the entry, and loads a fresh set without issuing a physical action. The gate
device ID and all entity unique IDs are preserved, including when the name or source
entities change.

There is no Options Flow in the MVP: every available setting affects the required
gate definition or its safety behavior and therefore belongs to Reconfigure Flow.

## Troubleshooting

### Cover is unavailable

At least one configured control entity is missing, `unknown`, or `unavailable`.
Restore the source integration/entity. No partial command sequence is started.

### Gate shows a limit-sensor conflict

Both endpoint sensors are active after inversion and debounce. Check wiring,
polarity, and entity states. Movement remains blocked until the conflict clears.

### Gate reports an opening or closing timeout

The configured endpoint did not activate within travel time plus its direction
margin. Check the gate mechanically, then verify the sensor and timing. A timeout
with a configured endpoint never means the endpoint was reached.

### External movement is not detected

Direction can be inferred only from authoritative endpoint evidence. With no usable
endpoint or ambiguous evidence, the integration deliberately avoids guessing.

### STOP is missing

The selected STOP strategy is **Unsupported**. Reconfigure a strategy only if it is
implemented by the physical controller and compatible with the selected sources.

## Development and verification

Install [uv](https://docs.astral.sh/uv/) and run:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy custom_components tests
uv run pytest
```

Product, architecture, state-machine, test, and implementation evidence is under
[`docs/`](docs/README.md). Current progress is recorded in
[`IMPLEMENTATION_TRACKER.md`](docs/docs/IMPLEMENTATION_TRACKER.md).

## License

[MIT](LICENSE)
