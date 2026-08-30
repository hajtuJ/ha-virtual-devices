# Virtual Devices

`Virtual Devices` is a standalone Home Assistant custom integration for composing existing Home Assistant entities into higher-level virtual devices.

The first supported device type is:

- **Virtual Gate**

The integration is designed to be installed through HACS and configured entirely from the Home Assistant UI.

## Project status

Initial development / MVP.

## Core idea

Existing Home Assistant entities:

```text
switch.gate_open
switch.gate_close
binary_sensor.gate_closed
binary_sensor.gate_open
```

are composed into one logical device:

```text
Device: Driveway Gate

cover.driveway_gate
sensor.driveway_gate_detailed_state
sensor.driveway_gate_last_direction
binary_sensor.driveway_gate_problem
```

## Architecture

This project is a **Home Assistant custom integration**, not:

- a Supervisor Add-on,
- an external backend,
- a NestJS application,
- a Nuxt application,
- a standalone automation server.

Runtime logic lives inside Home Assistant.

## Configuration

The integration should use native Home Assistant UI mechanisms:

- Config Flow
- Config Entries
- Config Subentries where appropriate
- Reconfigure Flow
- Options Flow where appropriate
- native entity/device selectors

Manual YAML configuration is not the primary configuration path.

## Repository structure

Target structure:

```text
virtual-devices/
├── custom_components/
│   └── virtual_devices/
│       ├── __init__.py
│       ├── manifest.json
│       ├── const.py
│       ├── config_flow.py
│       ├── cover.py
│       ├── sensor.py
│       ├── binary_sensor.py
│       ├── diagnostics.py
│       ├── gate/
│       │   ├── controller.py
│       │   ├── state_machine.py
│       │   ├── command_executor.py
│       │   ├── command_models.py
│       │   ├── position.py
│       │   ├── persistence.py
│       │   ├── models.py
│       │   └── validation.py
│       ├── translations/
│       │   ├── en.json
│       │   └── pl.json
│       └── strings.json
├── tests/
│   ├── conftest.py
│   ├── test_config_flow.py
│   ├── test_cover.py
│   ├── test_diagnostics.py
│   └── gate/
│       ├── test_state_machine.py
│       ├── test_command_executor.py
│       └── test_position.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── VIRTUAL_GATE_SPEC.md
│   ├── STATE_MACHINE.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── IMPLEMENTATION_TRACKER.md
│   └── TEST_PLAN.md
├── hacs.json
├── pyproject.toml
├── README.md
├── LICENSE
└── .github/
    └── workflows/
        ├── test.yml
        └── validate.yml
```

The exact structure may be adjusted if required by current Home Assistant or HACS conventions.

## Documentation

Before implementing Virtual Gate, read:

1. `docs/ARCHITECTURE.md`
2. `docs/VIRTUAL_GATE_SPEC.md`
3. `docs/STATE_MACHINE.md`
4. `docs/IMPLEMENTATION_PLAN.md`
5. `docs/IMPLEMENTATION_TRACKER.md`
6. `docs/TEST_PLAN.md`

## Home Assistant documentation

Always verify current APIs against:

https://developers.home-assistant.io/

Especially:

- Config Flow
- Config Subentries
- CoverEntity
- RestoreEntity
- Device Registry
- Entity Registry
- diagnostics
- translations
- selectors
