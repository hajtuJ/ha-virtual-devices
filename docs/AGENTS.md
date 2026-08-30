# AGENTS.md

## Project

This repository contains the Home Assistant custom integration:

`Virtual Devices`

The first device type is:

`Virtual Gate`

## Required reading

Before modifying Virtual Gate code, read:

- `docs/ARCHITECTURE.md`
- `docs/VIRTUAL_GATE_SPEC.md`
- `docs/STATE_MACHINE.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/IMPLEMENTATION_TRACKER.md`
- `docs/TEST_PLAN.md`

## Rules

- This is a Home Assistant custom integration, not a Supervisor Add-on.
- Do not introduce NestJS, Nuxt, external services, or another runtime without an explicit architecture decision.
- Prefer native HA Config Flow UI.
- Keep Home Assistant entity adapters thin.
- Keep gate state-machine logic independently testable.
- Preserve `last_direction` after STOP.
- Model STOP as a strategy.
- Never trigger physical movement automatically after startup/reload.
- Always guarantee cleanup for pulse/HOLD operations.
- Serialize gate commands.
- Treat physical endpoint sensors as more authoritative than time estimation.
- Do not auto-resolve sensor conflicts by moving the gate.
- Verify current Home Assistant APIs instead of relying on stale examples.
- Run relevant tests and validation before claiming work is complete.
