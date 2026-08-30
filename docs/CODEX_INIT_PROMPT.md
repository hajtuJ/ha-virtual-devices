# Codex initialization prompt — Virtual Devices

You are starting a brand-new standalone Git repository for a Home Assistant custom integration named:

`Virtual Devices`

The repository contains no legacy application architecture that must be preserved.

The first supported virtual device is:

`Virtual Gate`

Your job is to bootstrap the repository and implement the first MVP increment according to the project documentation.

## Read first

Before writing implementation code, read these files completely:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/VIRTUAL_GATE_SPEC.md`
- `docs/STATE_MACHINE.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/IMPLEMENTATION_TRACKER.md`
- `docs/TEST_PLAN.md`

Treat them as the current product and architecture specification.

## Repository purpose

This is a Home Assistant **custom integration** repository.

It is NOT:

- a Supervisor Add-on repository;
- a NestJS application;
- a Nuxt application;
- a standalone backend;
- a custom automation server.

Runtime logic must live inside Home Assistant under:

```text
custom_components/virtual_devices/
```

The integration should ultimately be installable through HACS.

## First task: repository bootstrap

Before substantive feature implementation:

1. create the clean repository structure;
2. choose and configure appropriate Python tooling;
3. add HACS metadata;
4. add Home Assistant manifest/config flow skeleton;
5. add GitHub Actions for validation/tests;
6. add test infrastructure;
7. verify current Home Assistant and HACS documentation before relying on specific APIs.

Do not blindly use stale examples from old HA integrations.

## UI approach

MVP configuration is native Home Assistant UI:

- Config Flow;
- Config Entries;
- Config Subentries if they are appropriate for the selected minimum HA version;
- Reconfigure Flow;
- Options Flow where appropriate;
- native entity selectors.

Do NOT build a custom frontend for the MVP.

Do NOT create NestJS or Nuxt.

A custom HA panel may be considered only in a later phase for a visual sequence editor.

## Architectural constraint

Do not put gate behavior directly inside `cover.py`.

Use a separation similar to:

```text
VirtualGateCoverEntity
        |
        v
GateController
        |
        +-- GateStateMachine
        +-- GateCommandExecutor
        +-- GatePositionEstimator
        +-- GatePersistence
        +-- source listeners
```

The state machine should be testable primarily without Home Assistant.

## Critical behavior

Virtual Gate must eventually support:

```text
OPEN
CLOSE
optional STOP

single step-by-step control
separate OPEN/CLOSE
separate OPEN/CLOSE/STOP

0/1/2 endpoint sensors
active-state inversion
sensor debounce

independent opening/closing times
independent timeout margins

pulse
hold
minimum command interval

direction-change strategy
repeated-command policy

external movement detection
estimated position
source availability
endpoint timeout
sensor conflict
safe restore
```

## Direction memory is mandatory

This state is valid and meaningful:

```text
state = STOPPED
last_direction = OPENING
estimated_position = 47
```

Do not discard `last_direction` when motion stops.

Step-by-step gate controllers depend on knowing the previous movement direction.

## STOP is a strategy

Never assume a third STOP relay exists.

The domain model must be capable of representing at least:

```text
DEDICATED
PULSE_SAME_DIRECTION
PULSE_OPPOSITE_DIRECTION
HOLD_SAME_DIRECTION
HOLD_OPPOSITE_DIRECTION
CUSTOM_SEQUENCE
UNSUPPORTED
```

If STOP is unsupported:

```text
CoverEntityFeature.STOP
```

must not be exposed.

## Safety requirements

This integration controls physical gates.

Mandatory rules:

1. Home Assistant startup/reload must never cause movement.
2. Conflicting endpoint sensors must never trigger automatic corrective movement.
3. If an endpoint sensor is configured, timeout must report a fault rather than assume endpoint success.
4. Pulse/HOLD execution must guarantee deactivation even during cancellation.
5. Serialize command execution.
6. Validate critical source availability before executing a sequence.
7. Never bypass physical gate safety devices.
8. Never advertise unsupported STOP behavior.
9. Avoid unsafe simultaneous OPEN/CLOSE output activation.

## Implementation order

Prefer:

1. repository bootstrap;
2. integration scaffold;
3. domain enums/models;
4. pure state machine;
5. state-machine unit tests;
6. command sequence abstraction;
7. command executor + tests;
8. configuration model;
9. Config Flow;
10. cover entity;
11. source entity listeners;
12. position estimation;
13. persistence;
14. diagnostics;
15. reconfigure/options;
16. translations;
17. HACS/public documentation;
18. complete CI validation.

## First worklog

Before beginning substantive implementation, report:

1. current Home Assistant minimum version you propose and why;
2. whether you recommend Config Subentries or one ConfigEntry per gate;
3. proposed repository tree;
4. selected test/lint tooling;
5. selected HACS validation approach;
6. any API assumptions you verified against current HA documentation.

Then begin implementation.

Do not wait for approval unless a genuinely blocking ambiguity prevents safe implementation.

## Scope

Implement only Virtual Gate initially.

Design naming so future device types can be added, but do not build speculative generic engines.

When you finish each increment:

- run tests;
- run lint/validation;
- report exactly what passed;
- report failures honestly;
- never claim an unexecuted check passed.
