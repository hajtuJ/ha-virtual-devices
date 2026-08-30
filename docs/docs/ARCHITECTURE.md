# Architecture — Virtual Devices

## 1. Purpose

`Virtual Devices` is a standalone Home Assistant custom integration.

Its purpose is to combine multiple existing Home Assistant entities, potentially originating from unrelated integrations, into one higher-level logical device.

Example:

```text
Zigbee relay
Nexwell binary input
Shelly relay
ESPHome sensor
        │
        ▼
Virtual Gate
        │
        ▼
cover.driveway_gate
```

The integration does not communicate directly with vendor hardware unless a future device type explicitly requires it.

## 2. Product direction

The project should initially support only:

- Virtual Gate

The architecture must remain extensible for future types:

- Virtual Garage Door
- Virtual Blind
- Virtual Pump
- Virtual Lock
- Virtual Climate
- other composite devices

Do not build a generic workflow engine before Virtual Gate works.

## 3. Runtime architecture

Recommended separation:

```text
Home Assistant
      │
      ▼
VirtualGateCoverEntity
      │
      ▼
GateController
      │
      ├── GateStateMachine
      ├── GateCommandExecutor
      ├── GatePositionEstimator
      ├── GatePersistence
      └── GateSourceObserver
```

### VirtualGateCoverEntity

Responsibilities:

- Home Assistant entity lifecycle;
- expose `cover`;
- map domain state to HA state;
- expose supported features;
- delegate commands.

It must NOT contain the full state machine.

### GateController

Responsibilities:

- orchestrate state machine;
- receive source entity events;
- execute commands;
- manage timers;
- expose current domain model;
- emit updates to HA entity.

### GateStateMachine

Responsibilities:

- deterministic state transitions;
- direction memory;
- timeout decisions;
- conflict detection;
- reaction to source events.

Prefer pure/testable logic.

### GateCommandExecutor

Responsibilities:

- pulse;
- hold;
- sequence execution;
- timing;
- serialization;
- cleanup;
- physical entity actions.

### GatePositionEstimator

Responsibilities:

- estimate position using configured travel times;
- stop/resume estimation;
- calibrate against limit sensors.

### GatePersistence

Responsibilities:

Persist safe semantic state such as:

```text
last_stable_state
last_direction
estimated_position
last_command
last_transition_timestamp
```

Never automatically resume physical movement after HA restart.

## 4. Integration type

The manifest should be evaluated for:

```json
"integration_type": "helper"
```

if this remains the correct Home Assistant classification at implementation time.

The agent must verify current HA documentation before finalizing the manifest.

## 5. Configuration architecture

The preferred user model is:

```text
Virtual Devices
├── Driveway Gate
├── Garden Gate
└── Garage Gate
```

Preferred implementation:

```text
one parent ConfigEntry
+
one ConfigSubentry per virtual device
```

if supported cleanly by the minimum HA version selected for this project.

If Config Subentries create material compatibility or lifecycle problems, multiple ConfigEntries are acceptable.

The decision must be documented in code and project documentation.

## 6. UI strategy

MVP uses native HA configuration UI.

Use:

- entity selectors;
- number selectors;
- boolean selectors;
- select selectors;
- Config Flow steps;
- Reconfigure Flow;
- Options Flow if suitable.

Do not build a custom frontend initially.

A custom panel may be considered later only if a visual command-sequence editor becomes materially more usable than Config Flow.

Even then:

- no external NestJS backend;
- no separate application runtime;
- the frontend remains an optional UI layer over the integration.

## 7. HACS

The repository is intended to be installable through HACS.

Required:

```text
hacs.json
custom_components/virtual_devices/manifest.json
README.md
GitHub releases/tags
```

CI should validate:

- integration structure;
- manifest;
- translations;
- tests;
- linting.

Use current HACS validation conventions.

## 8. Event-driven design

Virtual Devices should observe source entities using HA state-change listeners.

Avoid unnecessary polling.

Typical observed entities:

```text
open limit
closed limit
photocell
obstacle
motor running
power
```

Listeners and timers must always be removed on unload.

## 9. Concurrency

Gate movement control is timing-sensitive.

Command execution must be serialized.

Potentially dangerous case:

```text
OPEN task
+
CLOSE task
```

must never result in uncontrolled simultaneous relay activation.

Use a dedicated command lock / serialized executor.

All pulse/hold actions must use guaranteed cleanup.

Example principle:

```python
activate()
try:
    await sleep(...)
finally:
    deactivate()
```

## 10. Availability

Availability is separate from logical gate state.

A gate may be logically known as CLOSED but temporarily unable to accept commands because a source relay is unavailable.

The controller should track:

```text
logical state
control availability
sensor availability
active problem
```

Do not collapse every diagnostic issue into `unavailable`.

## 11. Safety

This integration controls physical gates.

Rules:

1. HA restart must never cause gate movement.
2. Conflicting limit sensors must never trigger automatic corrective movement.
3. Timeout with a configured limit sensor must be reported as a fault.
4. Command cancellation must not leave relays active.
5. Physical safety devices must not be bypassed.
6. CLOSE may optionally be blocked when a configured safety sensor is active.
7. Unsupported STOP must not be advertised by the HA cover entity.

## 12. Repository philosophy

This repository starts from zero.

Do not assume architecture from any previous Home Assistant projects.

Prefer:

- current Home Assistant patterns;
- straightforward Python;
- strong tests around state transitions;
- minimal external dependencies;
- no unnecessary framework abstractions.
