# Changelog

All notable changes to Virtual Devices are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

### Added

- Native Home Assistant Config Flow and Reconfigure Flow for independent Virtual
  Gates.
- Single step-by-step, separate OPEN/CLOSE, and separate OPEN/CLOSE/STOP controller
  topologies backed by switch or button entities.
- Serialized pulse, bounded HOLD, STOP, reversal, and repeated-command execution.
- Gate cover with truthful dynamic STOP support and no `SET_POSITION` capability.
- Zero, one, or two inverted/debounced endpoint sensors plus optional obstacle input.
- Event-driven external movement detection, asymmetric position estimation, endpoint
  timeout faults, and limit-conflict blocking.
- Restart-safe semantic persistence that never resumes movement, timers, or actions.
- Detailed-state, last-direction, last-command, and problem diagnostics plus a
  redacted config-entry diagnostics payload.
- English and Polish UI translations.
- Typed domain/state-machine/controller layers and comprehensive HA/safety tests.

### Safety

- Setup, unload, reload, restore, migration, and reconfigure issue no physical
  command.
- Command sequences are preflighted and serialized; OPEN/CLOSE outputs are
  interlocked.
- Cancellation, exceptions, source loss, and unload use guaranteed relay cleanup.
- Physical endpoints outrank estimates/history, and simultaneous endpoints block
  movement without automatic correction.

### Known release gates

- The GitHub repository must be public before HACS validation and installation.
- A non-moving/simulated Home Assistant UI test must pass and be documented.
- A controlled physical hardware test with certified safety systems must pass before
  the GitHub release and `v0.1.0` tag are published.

[0.1.0]: https://github.com/hajtuJ/ha-virtual-devices/releases/tag/v0.1.0
