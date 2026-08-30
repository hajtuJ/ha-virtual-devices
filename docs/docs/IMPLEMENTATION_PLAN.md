# Implementation Plan

## Phase 0 — New repository bootstrap

Create a clean standalone repository dedicated to:

```text
Virtual Devices
```

Initial repo should contain:

```text
custom_components/virtual_devices/
tests/
docs/
.github/workflows/
README.md
LICENSE
hacs.json
pyproject.toml
```

Choose a permissive open-source license unless project owner decides otherwise.

Do not copy runtime architecture from unrelated add-ons.

## Phase 1 — Tooling

Configure only tooling useful for a HA custom integration.

Recommended:

```text
pytest
pytest-homeassistant-custom-component
ruff
mypy only if it provides value without excessive friction
```

Verify current recommended Home Assistant custom integration testing conventions before pinning versions.

## Phase 2 — HACS baseline

Create:

```text
hacs.json
manifest.json
```

Validate repository against current HACS requirements.

Prepare GitHub Actions for:

```text
tests
lint
HACS validation
hassfest where applicable
```

## Phase 3 — Integration scaffold

Create the integration skeleton:

```text
custom_components/virtual_devices/
```

Minimum:

```text
__init__.py
manifest.json
const.py
config_flow.py
strings.json
translations/en.json
translations/pl.json
```

Do not add platforms until needed.

## Phase 4 — Domain model

Implement enums/models first.

Suggested:

```text
GateState
GateDirection
GateCommand
GateProblem

ControlMode
ControlActionType

StopStrategyType
DirectionChangeStrategyType
RepeatedCommandPolicy

CommandSequence
CommandStep
```

Keep this layer as independent from Home Assistant as practical.

## Phase 5 — State machine before UI

Implement:

```text
gate/state_machine.py
```

Then unit tests.

Minimum transitions:

```text
closed -> opening
opening -> open
open -> closing
closing -> closed

opening -> stopped
closing -> stopped

stopped preserves last_direction

opening -> closing
closing -> opening

external movement

timeouts

sensor conflict

restore
```

## Phase 6 — Command abstraction

Model commands as explicit sequences.

Example:

```text
Activate(source)
Delay(500ms)
Deactivate(source)
```

or:

```text
Pulse(source, 500ms)
Delay(800ms)
Pulse(other_source, 500ms)
```

State machine should not directly call Home Assistant services.

## Phase 7 — Command executor

Implement HA-side execution.

Requirements:

```text
pulse
hold
delay
serialization
minimum intervals
cancellation
cleanup
availability checks
```

Every activation requiring later deactivation must guarantee cleanup.

## Phase 8 — Config model

Define a serializable configuration model.

Avoid scattering raw ConfigEntry dict keys across the codebase.

Provide validation for:

```text
positive durations
required entities
conflicting source selections
invalid STOP strategy
invalid limit configuration
```

## Phase 9 — Config Flow

Basic UI:

```text
1. Name
2. Control mode
3. Source controls
4. Limit sensors
5. Opening/closing times
6. Create
```

Advanced/reconfigure:

```text
pulse duration
hold duration
command interval
STOP strategy
direction change
repeated command
margins
debounce
safety inputs
```

Use native HA selectors.

## Phase 10 — Config Entries model

Evaluate current HA Config Subentry support.

Preferred if clean:

```text
Virtual Devices ConfigEntry
    ├── Gate A subentry
    ├── Gate B subentry
    └── Gate C subentry
```

If it creates unnecessary complexity, use one ConfigEntry per Virtual Gate in MVP.

Favor maintainability over architectural novelty.

Document the decision.

## Phase 11 — Cover platform

Add:

```text
cover.py
```

Requirements:

```text
device_class=gate
OPEN
CLOSE
optional STOP
stable unique_id
DeviceInfo
availability
```

Delegate to GateController.

## Phase 12 — Source observation

Subscribe to HA state changes for:

```text
open limit
closed limit
optional safety sensors
optional motor-running sensor
```

No periodic polling of source entities unless required for a specific reason.

## Phase 13 — Position estimation

Implement optional estimator.

Keep it independent enough for deterministic tests.

Do not expose position setting until explicit support exists.

## Phase 14 — Persistence

Safely restore:

```text
last stable state
last direction
estimated position
last command
timestamps useful for diagnostics
```

Never auto-resume movement.

## Phase 15 — Diagnostics entities

Add recommended diagnostic entities:

```text
detailed state
last direction
last command
problem
```

Consider disabling secondary diagnostics by default.

## Phase 16 — Integration diagnostics

Add HA diagnostics payload.

Include:

```text
control mode
state
last direction
estimated position
last command
limit states
source availability
problem
```

Redact anything user-identifying if applicable.

## Phase 17 — Reconfigure

Support changing setup without deleting the integration/device.

Preserve:

```text
unique IDs
device identity
entity registry identity
```

where technically appropriate.

## Phase 18 — Documentation

Public README should include:

```text
What it does
Installation via HACS
Creating first Virtual Gate
Control modes
Limit sensors
STOP strategies
Travel-time estimation
External movement
Troubleshooting
Safety note
```

## MVP Definition of Done

MVP is complete when:

- repository is standalone and installable via HACS;
- Virtual Devices can be added from HA UI;
- at least two independent Virtual Gates can coexist;
- OPEN/CLOSE work;
- STOP is dynamically supported;
- 0/1/2 endpoint sensors are supported;
- active state inversion is supported;
- opening/closing times are independent;
- margins work;
- direction is remembered after STOP;
- external movement is detected when inferable;
- endpoint timeouts create faults;
- sensor conflicts create faults;
- HA restart does not cause motion;
- source entity unavailability is handled;
- pulse/HOLD cancellation cannot leave a relay active;
- Polish and English translations exist;
- tests and CI pass.
