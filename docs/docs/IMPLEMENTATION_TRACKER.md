# Virtual Devices — Implementation Tracker

This is the operational progress tracker for the Virtual Gate MVP. The product
requirements live in `VIRTUAL_GATE_SPEC.md`; architecture and sequencing live in
`ARCHITECTURE.md` and `IMPLEMENTATION_PLAN.md`. This file records what has actually
been completed and how it was verified.

## Current snapshot

- **Updated:** 2026-08-30
- **Release target:** MVP / `0.1.0`
- **Overall status:** `IN_PROGRESS`
- **Checklist progress:** 93 / 104 tasks (89%)
- **Current stage:** Stage 10 — hardening, CI, and MVP release
- **Next milestone:** complete release audit, simulated manual test, and public HACS validation

## Status rules

Use exactly these stage statuses:

- `NOT_STARTED` — no task in the stage is complete.
- `IN_PROGRESS` — at least one task is complete or actively being implemented.
- `BLOCKED` — work cannot continue; add an entry to **Active blockers**.
- `DONE` — every checkbox and the stage exit gate are complete with evidence.

Checkboxes are evidence-based:

- `[ ]` means not completed or not verified.
- `[x]` means implemented, reviewed against the specification, and verified.
- Never mark a task complete because code merely exists.
- When a check cannot run, leave the task open and record the reason.
- Update the snapshot, stage row, evidence, and change log in the same change that
  completes a task.

Progress percentage is `completed checkboxes / all stage checkboxes`, rounded down.
Do not count examples, exit gates, or the final MVP checklist a second time.

## Stage overview

| Stage | Scope | Status | Progress | Depends on |
| --- | --- | --- | ---: | --- |
| 0 | Decisions and baseline | `DONE` | 8 / 8 | — |
| 1 | Repository and tooling | `DONE` | 9 / 9 | Stage 0 |
| 2 | HA scaffold and HACS | `IN_PROGRESS` | 7 / 8 | Stage 1 |
| 3 | Domain model | `DONE` | 9 / 9 | Stage 2 |
| 4 | State machine | `DONE` | 10 / 10 | Stage 3 |
| 5 | Command model and executor | `DONE` | 10 / 10 | Stages 3–4 |
| 6 | Configuration model and UI | `DONE` | 10 / 10 | Stages 3 and 5 |
| 7 | Controller and HA entities | `DONE` | 11 / 11 | Stages 4–6 |
| 8 | Observation, position, restore, diagnostics | `DONE` | 10 / 10 | Stage 7 |
| 9 | Reconfigure, translations, and user docs | `DONE` | 9 / 9 | Stages 6–8 |
| 10 | Hardening, CI, and MVP release | `NOT_STARTED` | 0 / 10 | Stages 1–9 |

## Stage 0 — Decisions and implementation baseline

**Status:** `DONE`

**Goal:** remove compatibility ambiguity before creating runtime code.

- [x] Review the architecture, functional specification, state machine, test plan,
  bootstrap checklist, and repository instructions.
- [x] Select and document the minimum supported Home Assistant version.
- [x] Verify and document `ConfigEntry` versus parent entry plus Config Subentries.
- [x] Verify and document the manifest `integration_type`.
- [x] Decide the supported MVP source-action subset.
- [x] Decide the Python version and dependency versioning policy.
- [x] Decide whether strict type checking is included in the MVP toolchain.
- [x] Record the decisions in **Architecture decisions** below and relevant docs.

**Exit gate:** every compatibility-affecting decision is documented with an official
HA/HACS reference and does not weaken a safety invariant.

**Evidence:**

- 2026-08-30 — project documents and root `AGENTS.md` reviewed while creating this
  tracker.
- 2026-08-30 — current HA 2026.8 manifest, config-entry, device registry, Python,
  HACS, and testing conventions verified against the official documentation and
  upstream repositories.

## Stage 1 — Repository and tooling

**Status:** `DONE`

**Goal:** create a reproducible Python project with fast local feedback.

- [x] Create the target repository directories.
- [x] Add a suitable `.gitignore` and remove accidental platform artifacts.
- [x] Add the selected permissive `LICENSE`.
- [x] Add `pyproject.toml` with supported Python and project metadata.
- [x] Configure Ruff formatting and lint rules.
- [x] Configure pytest and async test support.
- [x] Add `pytest-homeassistant-custom-component` with compatible versions.
- [x] Add `tests/conftest.py` and a passing smoke test.
- [x] Document exact environment setup and local validation commands.

**Exit gate:** a clean environment can install dependencies and run the configured
smoke, lint, and formatting checks successfully.

**Evidence:**

- 2026-08-30 — `uv lock` and `uv sync --locked` resolved a Python 3.14.2
  environment with Home Assistant 2026.8.3.
- 2026-08-30 — Ruff lint/format, mypy, compileall, and pytest passed locally.

## Stage 2 — Home Assistant scaffold and HACS baseline

**Status:** `IN_PROGRESS`

**Goal:** produce a loadable, UI-discoverable custom integration skeleton.

- [x] Create `custom_components/virtual_devices/__init__.py` and `const.py`.
- [x] Create a valid custom-integration `manifest.json` with a version.
- [x] Create the initial `config_flow.py` and set `config_flow: true`.
- [x] Add `strings.json`, `translations/en.json`, and `translations/pl.json`.
- [x] Implement typed per-entry runtime data and entry setup/unload skeletons.
- [x] Add `hacs.json` matching current HACS requirements.
- [x] Add scaffold/config-flow tests that load the integration without movement.
- [ ] Pass applicable hassfest and HACS validation.

**Exit gate:** Home Assistant can load and unload the integration skeleton; the UI
flow opens; setup, reload, and unload execute no source action.

**Evidence:**

- 2026-08-30 — five scaffold/config-flow/lifecycle/translation tests passed on HA
  2026.8.3; the tests prove two entries receive distinct stable identities.
- 2026-08-30 — official `ghcr.io/home-assistant/hassfest:latest` reported one
  integration and zero invalid integrations. HACS Action remains unverified.

## Stage 3 — Gate domain model

**Status:** `DONE`

**Goal:** define typed, serializable concepts without HA service dependencies.

- [x] Implement gate state, direction, command, and problem enums.
- [x] Implement control mode and source-action types.
- [x] Implement STOP strategy types.
- [x] Implement direction-change strategy types.
- [x] Implement repeated-command policies.
- [x] Implement immutable state/event/effect models where practical.
- [x] Define serializable command sequence and step models.
- [x] Encode and validate core state invariants.
- [x] Add unit tests for serialization, validation, and invalid combinations.

**Exit gate:** domain imports do not require a running HA instance and all defined
invariants have deterministic unit tests.

**Evidence:**

- 2026-08-30 — domain enums, immutable snapshots/events/effects, and command
  sequences contain no Home Assistant imports.
- 2026-08-30 — twenty domain tests cover serialization round trips, invalid source
  combinations, timing validation, immutability, endpoints, and direction memory.

## Stage 4 — Pure gate state machine

**Status:** `DONE`

**Goal:** implement deterministic transitions before wiring the HA UI.

- [x] Implement CLOSED/OPEN/OPENING/CLOSING normal transitions.
- [x] Implement STOPPED while preserving `last_direction`.
- [x] Implement direction reversal through explicit effects/strategies.
- [x] Implement repeated-command policies and safe defaults.
- [x] Implement 0/1/2 endpoint sensor behavior and active-state inversion inputs.
- [x] Implement endpoint precedence and limit-sensor conflict handling.
- [x] Implement timeout outcomes with and without endpoint sensors.
- [x] Implement inferable external movement and `UNKNOWN_MOVING`.
- [x] Implement safe restore transitions without physical effects.
- [x] Add the full state-machine and safety regression test matrix.

**Exit gate:** all transitions in `STATE_MACHINE.md` pass pure unit tests, including
conflicts, restore, timeouts, reversals, and direction memory.

**Evidence:**

- 2026-08-30 — pure `GateStateMachine` implements command, endpoint, timeout,
  conflict, availability, obstacle, external-motion, and restore transitions without
  importing Home Assistant or performing physical actions.
- 2026-08-30 — twenty-eight deterministic tests cover normal transitions, every
  reversal family, repeated policies, inverted limits, conflicts, timeouts,
  direction memory, external motion, and passive restore.

## Stage 5 — Command abstraction and serialized executor

**Status:** `DONE`

**Goal:** translate state-machine effects into safe physical source actions.

- [x] Implement activate, deactivate, delay, pulse, HOLD, and sequence semantics.
- [x] Implement source adapters for the agreed MVP action subset.
- [x] Implement preflight validation of every critical source.
- [x] Serialize command execution with an explicit concurrent-command policy.
- [x] Enforce minimum command and pulse intervals.
- [x] Implement direction-change delays and multi-step strategies.
- [x] Guarantee deactivation through cancellation and exception paths.
- [x] Prevent simultaneous activation of mutually exclusive OPEN/CLOSE outputs.
- [x] Abort partial sequences safely when a critical source becomes unavailable.
- [x] Add deterministic executor tests for order, timing, cleanup, and concurrency.

**Exit gate:** tests prove that no cancellation, exception, overlap, or unavailable
source can leave an owned output active or start a known-invalid sequence.

**Evidence:**

- 2026-08-30 — the queue-based executor performs whole-sequence preflight,
  rechecks availability before each physical action, enforces timing and relay
  interlocks, and cleans up owned outputs in `finally`.
- 2026-08-30 — switch and button service adapters use blocking Home Assistant
  service calls; thirteen executor/adapter tests cover ordering, timing,
  cancellation, concurrency, unavailable sources, and mutual exclusion.

## Stage 6 — Configuration model and native UI

**Status:** `DONE`

**Goal:** configure multiple gates safely through Home Assistant's native UI.

- [x] Implement a versioned, typed, serializable gate configuration model.
- [x] Validate positive durations, margins, debounce, and intervals.
- [x] Validate source combinations and mutually exclusive outputs.
- [x] Validate limits, active states, and STOP/reversal strategy compatibility.
- [x] Implement the basic Config Flow steps and native selectors.
- [x] Implement advanced strategy and safety-input steps.
- [x] Prevent duplicate virtual gates with stable identities.
- [x] Implement the selected ConfigEntry/Subentry topology and lifecycle.
- [x] Add complete Config Flow success, error, abort, and duplicate tests.
- [x] Verify that configuration and validation never execute physical actions.

**Exit gate:** at least two independent valid gates can be configured via UI, invalid
or unsafe combinations are rejected, and all flow strings are translatable.

**Evidence:**

- 2026-08-30 — immutable schema-versioned `GateConfig` is the single persistence
  boundary for sources, limits, timing, strategies, identity, and safety behavior;
  its canonical representation is JSON serializable and round-trip tested.
- 2026-08-30 — the five-step native Config Flow uses translated entity, number,
  boolean, text, and select selectors; it supports all three controller modes,
  optional inverted/debounced limits, obstacle input, and advanced strategies.
- 2026-08-30 — twenty-seven model/flow tests cover three source topologies, timing
  bounds, unsafe combinations, success, errors, duplicate abort, two independent
  gates, lifecycle, and zero physical service calls during setup/unload.

## Stage 7 — Controller and Home Assistant entities

**Status:** `DONE`

**Goal:** expose the domain safely through HA while keeping adapters thin.

- [x] Implement `GateController` orchestration and update callbacks.
- [x] Implement `VirtualGateCoverEntity` with `CoverDeviceClass.GATE`.
- [x] Map cached domain state to cover properties without I/O.
- [x] Expose OPEN/CLOSE and dynamic STOP feature flags.
- [x] Keep `SET_POSITION` unavailable for the MVP.
- [x] Implement stable entity `unique_id` and translated entity naming.
- [x] Register one Device Registry device per virtual gate.
- [x] Attach every gate entity to the correct device and config entry/subentry.
- [x] Model logical state, availability, and active problem separately.
- [x] Forward and unload all platforms with current HA APIs.
- [x] Add cover, device/entity registry, delegation, and unload tests.

**Exit gate:** two gates operate independently in HA tests; supported features are
truthful; unload removes entities/tasks safely and causes no movement.

**Evidence:**

- 2026-08-30 — the entry-owned `GateController` keeps pure transitions separate
  from physical sequences, commits movement state only after executor success, emits
  cached update callbacks, and cancels/awaits active execution during unload.
- 2026-08-30 — the non-polling gate cover exposes only OPEN/CLOSE plus truthful
  configured STOP, uses stable device/entity identifiers, and maps cached domain
  state without I/O; two-gate HA tests prove independent service delegation and
  registry ownership.
- 2026-08-30 — controller regressions prove unavailable sources cause no action or
  false movement state, and unloading a 60-second switch pulse deactivates the relay
  before completion.

## Stage 8 — Source observation, position, restore, and diagnostics

**Status:** `DONE`

**Goal:** make runtime state accurate, explainable, and restart-safe.

- [x] Subscribe to source state changes without polling.
- [x] Implement configurable endpoint debounce and inversion.
- [x] Implement listener/timer registration with guaranteed unload cleanup.
- [x] Implement deterministic opening and closing position estimation.
- [x] Freeze on STOP and calibrate position at physical endpoints.
- [x] Persist safe semantic state and direction memory.
- [x] Restore using sensor authority without replaying motion or timers.
- [x] Implement detailed-state, last-direction, last-command, and problem entities.
- [x] Implement redacted config-entry diagnostics.
- [x] Add listener lifecycle, position, restore, diagnostics, and restart tests.

**Exit gate:** physical sensors outrank estimates and restored history; restart/reload
never moves the gate; no listener, timer, or task leaks remain after unload.

**Evidence:**

- 2026-08-30 — `GateSourceObserver` uses indexed HA state-change listeners,
  configurable stable-state debounce, active-state inversion, and explicit cleanup;
  control and observation availability remain independent cached values.
- 2026-08-30 — the injected-clock position estimator covers asymmetric travel,
  clamping, STOP freeze, and physical endpoint calibration; controller-owned HA
  timeout/interval callbacks are cancelled on endpoint, STOP, reversal, and unload.
- 2026-08-30 — versioned private HA storage contains semantic context only. Startup
  caches debounced physical inputs before one passive RESTORE, so saved movement is
  never resumed and an inactive initial limit cannot fabricate external movement.
- 2026-08-30 — translated enum/problem entities and redacted entry diagnostics expose
  state, direction, command, availability, endpoints, position, and problem without
  gate names, stable IDs, or source entity IDs.

## Stage 9 — Reconfigure, translations, and user documentation

**Status:** `DONE`

**Goal:** make configuration maintainable without deleting devices.

- [x] Implement Reconfigure Flow for required gate setup data.
- [x] Implement Options Flow only for genuinely optional preferences, if any.
- [x] Preserve config, device, and entity identities across reconfigure and rename.
- [x] Replace listeners/timers safely when source configuration changes.
- [x] Add and test config-entry migration when the stored schema requires it.
- [x] Synchronize complete English and Polish translations.
- [x] Document installation, first gate setup, modes, limits, and STOP strategies.
- [x] Document safety constraints, known limitations, and troubleshooting.
- [x] Add reconfigure, migration, identity, and translation tests/validation.

**Exit gate:** users can change supported settings without duplicate devices, stale
listeners, movement during reload, or untranslated UI strings.

**Evidence:**

- 2026-08-30 — the native multi-step Reconfigure Flow pre-populates every required
  setting, validates through `GateConfig`, preserves the stable device ID, updates
  entry data/title, and performs one controlled reload. There are no merely optional
  MVP preferences, so an Options Flow is intentionally not exposed.
- 2026-08-30 — HA tests change the name, control source, and endpoint sensor while
  proving stable config-entry/device/entity identity, zero physical service calls,
  removal of the old listener, and activation of the new listener.
- 2026-08-30 — config-entry minor-version migration normalizes canonical data without
  setting up the integration or calling a source. English/Polish flow, selector,
  entity, exception, and reconfigure translations have identical validated shapes.
- 2026-08-30 — the public README now documents HACS/development installation, first
  setup, all modes/strategies, endpoints, estimation, external movement, restore,
  diagnostics, reconfigure, safety constraints, limitations, and troubleshooting.

## Stage 10 — Hardening, CI, and MVP release

**Status:** `NOT_STARTED`

**Goal:** prove the complete MVP is safe, reproducible, and releasable through HACS.

- [ ] Run and pass the complete test suite.
- [ ] Run and pass Ruff formatting and lint checks.
- [ ] Run and pass translation and structure validation.
- [ ] Run and pass HACS validation and applicable hassfest checks.
- [ ] Add CI workflows for tests, lint, HACS, and structure validation.
- [ ] Verify all safety regressions listed in `TEST_PLAN.md`.
- [ ] Perform a documented manual test on a non-moving/simulated HA setup first.
- [ ] Perform a documented controlled hardware test with physical safety systems.
- [ ] Finalize changelog/release notes and semantic version `0.1.0`.
- [ ] Tag and publish the HACS-compatible MVP release.

**Exit gate:** CI is green from a clean checkout, all MVP acceptance criteria pass,
and release evidence is linked below.

**Evidence:** _none yet._

## MVP acceptance checklist

This section is a release gate and is not included in the 104-task progress count.
Every item must be supported by completed stage tasks and test evidence.

- [ ] Installable as a HACS custom integration.
- [ ] Configurable entirely from native HA UI.
- [ ] At least two independent gates coexist.
- [ ] OPEN/CLOSE work and STOP support is truthful and dynamic.
- [ ] Zero, one, or two inverted/debounced endpoint sensors work.
- [ ] Direction remains known after STOP where evidence exists.
- [ ] Independent travel times/margins and estimated position work.
- [ ] External movement is detected when inferable.
- [ ] Endpoint timeouts and limit conflicts report faults safely.
- [ ] Required unavailable sources reject commands before partial execution.
- [ ] Pulse/HOLD cancellation and unload cannot leave outputs active.
- [ ] Startup, restore, reload, migration, and reconfigure cause no movement.
- [ ] Stable device/entity identities survive restart and reconfigure.
- [ ] English and Polish UI, diagnostics, user docs, tests, and CI are complete.

## Architecture decisions

Record decisions that affect compatibility, persistence, or physical behavior.

| ID | Date | Status | Decision | Rationale and evidence |
| --- | --- | --- | --- | --- |
| ADR-001 | 2026-08-30 | `ACCEPTED` | Minimum HA is 2026.8.0. | New integration targets the current stable HA generation and its single-entry device ownership model. HACS declares this minimum explicitly. |
| ADR-002 | 2026-08-30 | `ACCEPTED` | One ConfigEntry per Virtual Gate. | Gates share no account, connection, or hub resource; independent entries give simpler lifecycle, identity, reload, and failure isolation than a synthetic parent with subentries. |
| ADR-003 | 2026-08-30 | `ACCEPTED` | Manifest uses `integration_type: helper` and `iot_class: calculated`. | The integration composes existing HA entities into a calculated helper entity; this matches current core helper manifests. |
| ADR-004 | 2026-08-30 | `ACCEPTED` | MVP source actions are switch activation/deactivation and button press. | These cover common relay and momentary-input controllers. The domain action model remains extensible; arbitrary scripts, covers, and custom sequences are deferred. |
| ADR-005 | 2026-08-30 | `ACCEPTED` | Python 3.14.2+, exact development pins, uv lockfile, Ruff, pytest, and mypy. | HA 2026.8.3 requires Python 3.14.2. Exact test pins reproduce the supported HA patch level; runtime has no third-party dependencies. Strict typing starts with project-owned code. |

## Active blockers

| Since | Stage | Blocker | Owner / next action |
| --- | --- | --- | --- |
| 2026-08-30 | 2 | HACS Action cannot validate a private repository; HACS publishing requires a public GitHub repository. | Repository owner: make the repository public before HACS/release validation. Implementation may continue independently. |

## Verification log

Append commands and results that support completed work. Link CI runs or issues when
available. Do not replace failed results; add a later passing entry.

| Date | Stage | Command / check | Result | Evidence |
| --- | --- | --- | --- | --- |
| 2026-08-30 | 0 | Documentation consistency review | PASS | Tracker mapped to the project specifications. |
| 2026-08-30 | 1–2 | `uv sync --locked` | PASS | Python 3.14.2, HA 2026.8.3, 146 packages installed from the lockfile. |
| 2026-08-30 | 1–2 | `ruff check .` and `ruff format --check .` | PASS | All checks passed; 18 files formatted. |
| 2026-08-30 | 1–3 | `mypy custom_components tests` | PASS | Strict typing found no issues in twelve Python source files. |
| 2026-08-30 | 1–3 | `pytest` | PASS | Twenty-five tests passed. |
| 2026-08-30 | 2 | HA hassfest container | PASS | One integration; zero invalid integrations. |
| 2026-08-30 | 1–5 | `ruff check custom_components tests` and `ruff format --check custom_components tests` | PASS | All project Python files pass lint and formatting checks. |
| 2026-08-30 | 3–5 | `mypy custom_components tests/gate` | PASS | Strict typing found no issues in fifteen source files. |
| 2026-08-30 | 1–5 | `pytest -q` | PASS | Sixty-six tests passed. |
| 2026-08-30 | 2 | GitHub Actions Test + hassfest jobs | PASS | Test run 33319589919 and hassfest job 99279102703 passed on commit `559548d`. |
| 2026-08-30 | 2 | GitHub Actions HACS job | BLOCKED | Job 99279102520 cannot inspect the private repository through HACS; publication requires public visibility. |
| 2026-08-30 | 1–6 | `ruff check`, `ruff format --check`, and strict `mypy` | PASS | All twenty Python source/test files pass static validation. |
| 2026-08-30 | 1–6 | `pytest -q` | PASS | Ninety tests passed, including twenty-seven configuration tests. |
| 2026-08-30 | 2, 6 | `ghcr.io/home-assistant/hassfest:latest` | PASS | One integration, zero invalid integrations; translations and Config Flow validated. |
| 2026-08-30 | 1–7 | Ruff, strict mypy, compileall, and `pytest -q` | PASS | All static checks passed; ninety-six tests passed. |
| 2026-08-30 | 2, 7 | `ghcr.io/home-assistant/hassfest:latest` | PASS | One integration, zero invalid integrations; cover platform and exception translations validated. |
| 2026-08-30 | 7 | GitHub Actions Test run 33328492154 | PASS | Ruff, formatting, strict mypy, and all ninety-six tests passed for commit `7a9a0b3`. |
| 2026-08-30 | 2, 7 | GitHub Actions Validate run 33328492166 | PARTIAL | hassfest job 99302741814 passed; HACS job 99302741944 remained blocked by private-repository file access. |
| 2026-08-30 | 1–8 | Ruff, strict mypy, compileall, and `pytest -q` | PASS | All static checks passed; 108 tests passed including observer, estimator, persistence, restore, diagnostics, and lifecycle regressions. |
| 2026-08-30 | 2, 8 | `ghcr.io/home-assistant/hassfest:latest` | PASS | One integration, zero invalid integrations; all three platforms and synchronized translations validated. |
| 2026-08-30 | 8 | GitHub Actions Test run 33329113923 | PASS | Ruff, formatting, strict mypy, and all 108 tests passed for commit `8390c35`. |
| 2026-08-30 | 2, 8 | GitHub Actions Validate run 33329113904 | PARTIAL | hassfest job 99304368133 passed; HACS job 99304368071 remained blocked by private-repository file access. |
| 2026-08-30 | 1–9 | Ruff, strict mypy, compileall, and `pytest -q` | PASS | All static checks passed; 110 tests passed including reconfigure, identity, listener replacement, migration, and translation structure. |
| 2026-08-30 | 2, 9 | `ghcr.io/home-assistant/hassfest:latest` | PASS | One integration, zero invalid integrations; Reconfigure Flow and synchronized translations validated. |

## Progress change log

| Date | Change | Progress |
| --- | --- | ---: |
| 2026-08-30 | Created tracker; confirmed existing specification baseline. | 1 / 104 (1%) |
| 2026-08-30 | Accepted the five bootstrap architecture decisions. | 8 / 104 (7%) |
| 2026-08-30 | Completed tooling and all locally verifiable scaffold tasks. | 24 / 104 (23%) |
| 2026-08-30 | Completed the typed, immutable Virtual Gate domain model. | 33 / 104 (31%) |
| 2026-08-30 | Completed the pure gate state machine and safety regression matrix. | 43 / 104 (41%) |
| 2026-08-30 | Completed the serialized, cancellation-safe command executor and HA source adapter. | 53 / 104 (50%) |
| 2026-08-30 | Completed versioned configuration, native UI flow, validation, and translations. | 63 / 104 (60%) |
| 2026-08-30 | Completed the safe gate controller, cover platform, device ownership, and unload cleanup. | 74 / 104 (71%) |
| 2026-08-30 | Completed observation, estimation, semantic restore, diagnostic entities, and redacted diagnostics. | 84 / 104 (80%) |
| 2026-08-30 | Completed safe reconfiguration, migration, synchronized translations, and user documentation. | 93 / 104 (89%) |
