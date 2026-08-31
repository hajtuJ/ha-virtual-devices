# Virtual Gate 0.1.0 — Release Test Record

This record separates automated proof, simulated manual testing, and physical
hardware validation. A release gate is complete only when its evidence is recorded
below.

## Automated validation

- **Environment:** Python 3.14.2, Home Assistant 2026.8.3
- **Static checks:** Ruff lint/format, strict mypy, compileall
- **Runtime tests:** full pytest suite
- **HA structure:** official hassfest container
- **HACS:** pending public repository visibility

Exact commands, counts, CI run IDs, and outcomes are maintained in
`IMPLEMENTATION_TRACKER.md`.

## Simulated Home Assistant test

**Status:** `INCOMPLETE — local browser policy blocked the integration UI flow`

Required procedure:

1. Start a clean local Home Assistant using this repository's custom component.
2. Register simulated switch/button and binary-sensor entities only; do not connect
   motor or relay hardware.
3. Create a gate through the native UI and confirm device/entity creation.
4. Exercise OPEN, CLOSE, configured STOP, endpoint changes, obstacle blocking,
   unavailable control, conflicting limits, reload, and reconfigure.
5. Confirm service-call order, absence of unexpected calls during lifecycle actions,
   and cleanup of active switch outputs.
6. Record date, HA version, configuration, observations, and PASS/FAIL below.

**Evidence (2026-08-30):** Home Assistant 2026.8.3 started successfully from a
clean disposable configuration with the repository mounted as a custom component.
The simulated switch and limit/obstacle binary sensors loaded, and a disposable
local user completed the initial onboarding flow. After Home Assistant restarted to
apply its HTTP configuration, the Codex in-app browser security policy rejected
reloading `http://127.0.0.1:8124`; the Virtual Devices Config Flow and command
exercise therefore could not be completed. The temporary HA configuration and its
credentials were moved to the system Trash after shutdown. Repeat this procedure in
a local browser that permits loopback navigation before release.

## Controlled physical hardware test

**Status:** `PENDING — requires repository owner and physical test environment`

Prerequisites:

- simulated test is PASS;
- certified physical safety systems are installed and operational;
- test area is controlled and clear;
- emergency disconnect and manual stop are available;
- controller documentation has been checked against configured strategies.

Required procedure:

1. Verify setup/restart/reload/reconfigure produce no output pulse with motor safely
   isolated.
2. Verify each switch pulse/HOLD returns inactive after success, cancellation, and
   induced source failure.
3. Verify OPEN/CLOSE/STOP and each configured reversal behavior individually.
4. Verify endpoints, inversion, debounce, obstacle blocking, timeout, and conflict.
5. Verify external/manual/RF movement inference.
6. Reconnect the motor only under the approved controlled test plan and repeat the
   supported command paths.

**Evidence:** _not run yet._

## Publication

**Status:** `PENDING`

After every test above passes:

1. Make the GitHub repository public.
2. Run HACS Action and hassfest successfully without ignored checks.
3. Confirm manifest and project versions are `0.1.0`.
4. Change the changelog date from `Unreleased` to the release date.
5. Create signed/annotated tag `v0.1.0`.
6. Publish a full GitHub release using the 0.1.0 changelog notes.
