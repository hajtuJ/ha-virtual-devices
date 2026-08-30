# AGENTS.md

## Scope and intent

These instructions apply to the entire repository. More deeply nested `AGENTS.md`
files may add local constraints, but they must not weaken the safety invariants in
this file.

This repository contains **Virtual Devices**, a Home Assistant custom integration
distributed through HACS. The first and only in-scope device type for the MVP is
**Virtual Gate**. It composes existing Home Assistant entities into a higher-level
virtual gate; it does not communicate with gate hardware directly.

This is not a Supervisor add-on, external backend, NestJS/Nuxt application, or a
standalone automation service. Runtime code belongs under
`custom_components/virtual_devices/` and runs inside Home Assistant.

## Required context

Before implementing or reviewing behavior, read the relevant documents completely.
For Virtual Gate work, the required reading order is:

1. `docs/README.md`
2. `docs/docs/ARCHITECTURE.md`
3. `docs/docs/VIRTUAL_GATE_SPEC.md`
4. `docs/docs/STATE_MACHINE.md`
5. `docs/docs/IMPLEMENTATION_PLAN.md`
6. `docs/docs/IMPLEMENTATION_TRACKER.md`
7. `docs/docs/TEST_PLAN.md`
8. `docs/docs/REPO_BOOTSTRAP.md` for bootstrap, tooling, packaging, or CI work

Treat those files as the product and architecture specification. This root file
defines repository-wide engineering and safety rules. When requirements conflict,
prefer, in order: physical safety, explicit product behavior, current Home Assistant
APIs, then implementation convenience. Surface unresolved contradictions instead of
silently choosing behavior.

Home Assistant evolves quickly. Before using or changing an HA API, verify the
current official developer documentation and the minimum supported HA version; do
not copy stale integration examples. Useful starting points:

- https://developers.home-assistant.io/docs/creating_component_index/
- https://developers.home-assistant.io/docs/creating_integration_manifest/
- https://developers.home-assistant.io/docs/config_entries_index/
- https://developers.home-assistant.io/docs/core/integration/config_flow/
- https://developers.home-assistant.io/docs/core/entity/
- https://developers.home-assistant.io/docs/core/entity/cover/
- https://developers.home-assistant.io/docs/core/integration-quality-scale/
- https://developers.home-assistant.io/docs/asyncio_index/

Document consequential compatibility decisions, especially the minimum HA version,
Config Subentries versus one ConfigEntry per gate, and manifest `integration_type`.

## Product boundaries

- Implement Virtual Gate first. Keep naming extensible, but do not build a generic
  workflow engine or speculative future device types.
- Use native HA UI configuration: Config Flow, Reconfigure Flow, Options Flow only
  for genuinely optional preferences, Config Subentries when justified, and native
  selectors. Manual YAML is not the primary configuration path.
- Do not add a custom frontend, external service, or second runtime for the MVP.
- Keep dependencies minimal. Prefer Home Assistant helpers and the standard library.
- Model source controls as actions rather than assuming every source is a `switch`.
  The first UI may support a deliberately narrower subset of actions.

## Architecture

Keep Home Assistant adapters thin and domain behavior independently testable:

```text
VirtualGateCoverEntity
        |
        v
GateController
        +-- GateStateMachine
        +-- GateCommandExecutor
        +-- GatePositionEstimator
        +-- GatePersistence
        +-- GateSourceObserver
```

- Entity platforms own HA entity lifecycle, state mapping, supported features, and
  command delegation. Do not put the gate state machine in `cover.py`.
- `GateController` orchestrates domain components, listeners, timers, commands, and
  update callbacks.
- `GateStateMachine` must be deterministic and as independent of HA as practical.
  It decides transitions and effects; it must not call HA services.
- `GateCommandExecutor` is the only layer that performs physical source actions. It
  owns serialization, timing, preflight checks, cancellation, and cleanup.
- `GatePositionEstimator` uses injected/controllable time and remains deterministic
  in tests.
- `GatePersistence` stores only safe semantic context. Restoring context must never
  resume movement or replay a command.
- Use serializable, typed configuration/domain models. Do not scatter raw config
  dictionary keys throughout the integration.
- Keep persisted config separate from runtime objects. Store typed per-entry runtime
  data in `ConfigEntry.runtime_data`, not an untyped global `hass.data` bucket.

## Non-negotiable physical-safety invariants

This integration controls a physical gate. Any code path that can activate a source
is safety-critical.

1. Setup, startup, reload, unload, reconfigure, migration, and restore must never
   cause physical movement or replay a previous pulse/HOLD/sequence.
2. Serialize physical command sequences. Concurrent OPEN/CLOSE/STOP requests must
   follow an explicit policy and must never activate mutually exclusive outputs
   simultaneously.
3. Preflight all critical source availability and configuration before the first
   action. Do not start a sequence that is already known to be impossible to finish.
4. Every activation that requires deactivation must use guaranteed cleanup (for
   example `try/finally`). Cancellation, timeout, unload, and exceptions must not
   leave a relay active.
5. A partially executed sequence must fail safely. Never continue blindly when a
   critical source becomes unavailable.
6. Both endpoint sensors active is `LIMIT_SENSOR_CONFLICT`: block movement by
   default, report the problem, and never auto-move to resolve it.
7. Physical endpoint sensors outrank observed motion, time estimates, restored
   history, and assumptions. Debounce configured sensors before accepting changes.
8. If the relevant endpoint sensor exists, expiration of travel time plus margin is
   a fault; it must not fabricate OPEN or CLOSED. Without that endpoint sensor, time
   estimation may establish the endpoint as specified.
9. Never bypass, suppress, or simulate physical gate safety systems. A configured
   obstacle/photocell may block CLOSE, but software is not a substitute for certified
   hardware protection.
10. Do not expose `CoverEntityFeature.STOP` unless the configured STOP strategy is
    actually supported and implemented. Do not expose `SET_POSITION` until movement
    to a requested position is implemented and tested end to end.

Safety-related behavior changes require focused regression tests, including failure,
cancellation, unload/reload, conflicting-sensor, and unavailable-source paths.

## Gate domain rules

- Preserve both `current_direction` and `last_direction`. STOPPED sets
  `current_direction=UNKNOWN` and retains the previous `last_direction`.
- A valid state is `STOPPED`, `last_direction=OPENING`, position `47`; do not flatten
  it to a generic open/unknown state internally.
- STOP is a strategy, never an assumption about a dedicated relay. Support the domain
  distinction among dedicated, same/opposite-direction pulse or HOLD, custom
  sequence, and unsupported behavior.
- Direction reversal and repeated commands use explicit configured strategies. Safe
  defaults ignore redundant commands.
- Track logical state, command availability, sensor availability, and active problem
  separately. Do not make an entity unavailable merely because one non-critical
  diagnostic source is unavailable.
- Detect external movement only when evidence supports the direction. Use
  `UNKNOWN_MOVING` when it cannot be inferred safely.
- Opening and closing travel times and margins are independent. Clamp estimated
  position to `0..100`, freeze it on STOP, and recalibrate it at physical endpoints.
- State transitions and physical effects should be explicit. A rejected transition
  must not leak into a source action.

## Home Assistant implementation practices

- Prefer fully async integration code and HA `async_*` APIs. Never block the event
  loop; offload unavoidable blocking work with the HA executor helpers.
- Entity properties must be cheap, side-effect-free, and return cached in-memory
  values only. Source observation is push/event-driven, so entities normally set
  `_attr_should_poll = False` and schedule state writes when the controller changes.
- Register state listeners and timers with HA helpers. Attach cleanup callbacks to
  config-entry/entity unload (`entry.async_on_unload(...)` or the appropriate entity
  lifecycle hook). Reloads must not duplicate listeners or timers.
- Set up platforms with `async_forward_entry_setups` and unload every forwarded
  platform. Cancel controller tasks and safely deactivate owned outputs during
  teardown without initiating new movement.
- Never mutate `ConfigEntry.data` or `.options` directly; use HA config-entry update
  APIs. Add and test `async_migrate_entry` whenever stored schema versions change.
- Use Reconfigure Flow for required setup data and Options Flow only for optional
  runtime preferences. Validate durations, entity combinations, active states,
  strategy compatibility, and duplicate devices before creating/updating an entry.
- If Config Subentries are selected, use their current lifecycle APIs and give each
  virtual device stable identity. Otherwise, use one ConfigEntry per gate. Do not
  introduce subentries without confirming support in the declared minimum HA version.
- Every entity has a stable, deterministic `unique_id` independent of mutable names
  and `entity_id`. Each gate has one Device Registry device with stable identifiers;
  all its entities attach to it.
- New entities use `_attr_has_entity_name = True`, translation keys, appropriate
  device classes, and entity categories. Diagnostic entities should use
  `EntityCategory.DIAGNOSTIC`; secondary diagnostics should generally be disabled by
  default.
- The primary entity derives from `CoverEntity`, uses `CoverDeviceClass.GATE`, maps
  cached domain state through cover properties, and exposes feature flags dynamically.
- Availability describes whether HA can read/control the relevant functionality; it
  is not a replacement for detailed problem state. Raise current, translatable HA
  service/action exceptions for rejected user commands where applicable.
- Diagnostics must be useful and redact entity IDs, names, locations, or other user
  data when appropriate. Never log secrets or dump the entire config entry.
- The custom integration manifest must include a valid SemVer/CalVer `version`,
  `config_flow: true`, correct domain, documentation/issue URLs, and an explicitly
  verified integration type (likely `helper`, but verify before finalizing).
- Use the Integration Quality Scale as an engineering checklist even though this is
  a custom integration. Do not claim a tier or mark a rule complete without evidence.

## Configuration and translations

- Store canonical enum/config values, not localized labels.
- Keep `strings.json` and every shipped translation structurally synchronized.
  English and Polish are required for the MVP.
- All user-facing flow titles, labels, descriptions, errors, abort reasons, entity
  names, and service/action errors must be translatable.
- Preserve stable device/entity identity across reconfigure. Renaming a gate must not
  create a duplicate device or change unique IDs.
- Validate at both the UI boundary and domain boundary. Never rely on selectors alone
  to guarantee safety-critical validity.

## Testing and verification

Use the commands configured by the repository once `pyproject.toml` and workflows
exist; inspect them rather than inventing alternatives. The intended baseline is
`pytest`, `pytest-homeassistant-custom-component`, Ruff, HACS validation, and hassfest
where applicable.

- Start with pure unit tests for domain models, state machine, strategies, position,
  and command sequencing. Add HA tests for config flows, entity mapping, registries,
  lifecycle, diagnostics, restore, and reconfigure.
- Use controllable clocks/events and short deterministic awaits. Do not make unit
  tests depend on real travel-duration sleeps.
- Assert effects as well as state: activation order, deactivation in `finally`, no
  overlapping outputs, no command on setup/restore, and no leftover listeners/tasks.
- Cover the complete matrix in `docs/docs/TEST_PLAN.md`, especially direction memory,
  0/1/2 limits, inversion/debounce, external movement, endpoint timeout, sensor
  conflict, unavailable sources, cancellation, and multiple independent gates.
- A bug fix requires a regression test when practical. A new state transition or
  strategy requires table-driven success and failure tests.
- Run the narrowest relevant checks while iterating, then the full available test,
  lint, translation, HACS, and structure validation suite before completion.
- Report exactly which commands ran and their outcomes. Never claim an unexecuted
  check passed. If a check cannot run, explain why and what remains unverified.

## Change discipline

- Follow the implementation phases in `docs/docs/IMPLEMENTATION_PLAN.md`; keep each
  increment small and working. State machine and executor behavior precede a rich UI.
- Preserve existing user changes. Do not perform unrelated rewrites or destructive
  git operations.
- Keep code typed, readable, and direct. Add comments for safety rationale and
  non-obvious HA lifecycle behavior, not for syntax.
- Update product docs, translations, diagnostics, configuration migration, and tests
  together with the behavior they describe.
- Adding a dependency, changing persisted config, changing minimum HA, changing
  ConfigEntry/Subentry topology, or altering a physical command strategy is an
  architectural decision and must be documented.

## Definition of done

A change is complete only when its behavior matches the specifications, safety
invariants remain true, lifecycle cleanup is proven, relevant tests and validations
pass, user-visible text is translated, and documentation reflects the result. For
the full MVP completion criteria, use `docs/docs/IMPLEMENTATION_PLAN.md`. Update
`docs/docs/IMPLEMENTATION_TRACKER.md` with the status and verification evidence in
the same change.
