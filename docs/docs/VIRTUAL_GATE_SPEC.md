# Virtual Gate — Functional Specification

## 1. Goal

`Virtual Gate` combines existing Home Assistant entities into a single logical gate device.

Example source entities:

```text
switch.gate_open
switch.gate_close
binary_sensor.gate_closed
binary_sensor.gate_open
binary_sensor.gate_photocell
```

Result:

```text
Device: Driveway Gate

cover.driveway_gate
sensor.driveway_gate_detailed_state
sensor.driveway_gate_last_direction
sensor.driveway_gate_last_command
binary_sensor.driveway_gate_problem
```

## 2. Primary entity

Required:

```text
cover.<name>
```

The entity should use the Home Assistant gate cover device class.

Supported features must be dynamic.

Expected basic features:

```text
OPEN
CLOSE
STOP  # only when configured
```

Do not advertise `STOP` when STOP strategy is unsupported.

Do not add `SET_POSITION` to the MVP unless position-based movement is explicitly implemented and tested.

## 3. Control modes

### 3.1 Single step-by-step

One source control.

Physical controller may implement a sequence similar to:

```text
CLOSED  + pulse -> OPENING
OPENING + pulse -> STOPPED
STOPPED + pulse -> CLOSING
CLOSING + pulse -> STOPPED
STOPPED + pulse -> OPENING
```

The exact behavior must be configurable.

### 3.2 Separate OPEN / CLOSE

Two source controls:

```text
OPEN
CLOSE
```

STOP can use another strategy.

### 3.3 Separate OPEN / CLOSE / STOP

Three source controls.

### 3.4 Custom strategy

Architecture should allow custom command sequences later.

MVP does not need a full visual sequence builder.

## 4. Source control abstraction

Do not hard-code all commands to `switch`.

The model should be capable of representing actions such as:

```text
switch on/off
button press
script call
cover service
future HA action abstraction
```

MVP UI may intentionally support a narrower subset.

## 5. Pulse

Parameters:

```text
pulse_duration_ms
minimum_command_interval_ms
```

Example:

```text
pulse_duration_ms = 500
minimum_command_interval_ms = 700
```

## 6. HOLD

Pulse and hold are different concepts.

Example:

```text
hold_duration_ms = 2200
```

The integration must support both from the domain-model level.

## 7. STOP strategy

Supported conceptual strategies:

```text
DEDICATED
PULSE_SAME_DIRECTION
PULSE_OPPOSITE_DIRECTION
HOLD_SAME_DIRECTION
HOLD_OPPOSITE_DIRECTION
CUSTOM_SEQUENCE
UNSUPPORTED
```

Behavior may depend on the current movement state.

Examples:

```text
STOP while OPENING
STOP while CLOSING
STOP while STOPPED
STOP while OPEN
STOP while CLOSED
```

Safe default for STOP while not moving:

```text
IGNORE
```

unless explicitly configured otherwise.

## 8. Direction memory

Direction history is required.

Model:

```text
state
current_direction
last_direction
last_command
movement_started_at
movement_elapsed
estimated_position
```

Example:

```text
state = STOPPED
current_direction = UNKNOWN
last_direction = OPENING
estimated_position = 47
```

`last_direction` must survive STOP.

It should also be persisted across HA restart when safe to do so.

## 9. Limit sensors

Supported:

```text
no limits
CLOSED only
OPEN only
OPEN + CLOSED
```

Each configured limit:

```text
entity_id
active_state
debounce_ms
```

Example:

```text
entity_id = binary_sensor.driveway_gate_closed
active_state = on
debounce_ms = 300
```

## 10. State authority

Preferred state authority:

```text
physical limit sensors
>
observed movement information
>
time estimation
>
restored historical state
>
unknown
```

## 11. Travel timing

Separate configuration:

```text
opening_time_ms
closing_time_ms
opening_margin_ms
closing_margin_ms
```

Do not assume symmetric motion.

## 12. Endpoint timeout

When the relevant endpoint limit is configured:

```text
travel_time + margin
```

expires without limit activation:

```text
OPENING_TIMEOUT
```

or:

```text
CLOSING_TIMEOUT
```

Do not mark the gate as OPEN/CLOSED solely from elapsed time when an endpoint limit exists.

When no endpoint limit exists, elapsed time may determine the final state.

## 13. Position estimation

Optional estimate:

```text
0 = closed
100 = open
```

Opening:

```text
new_position =
start_position +
elapsed / opening_time
```

Closing:

```text
new_position =
start_position -
elapsed / closing_time
```

After STOP:

```text
freeze estimated position
```

After physical endpoint:

```text
CLOSED -> 0
OPEN -> 100
```

## 14. Direction change strategy

Conceptual strategies:

```text
DIRECT
STOP_THEN_REVERSE
STOP_WAIT_REVERSE
MULTI_PULSE
CUSTOM_SEQUENCE
UNSUPPORTED
```

Parameters may include:

```text
direction_change_delay_ms
pulse_count
pulse_interval_ms
```

Example:

```text
OPENING
CLOSE requested

STOP
wait 800ms
CLOSE
```

## 15. Repeated command policy

Must be configurable.

Cases:

```text
OPEN while OPENING
CLOSE while CLOSING
OPEN while OPEN
CLOSE while CLOSED
```

Policies:

```text
IGNORE
REPEAT
STOP
CUSTOM_SEQUENCE
```

Safe defaults:

```text
OPEN while OPENING -> IGNORE
CLOSE while CLOSING -> IGNORE
OPEN while OPEN -> IGNORE
CLOSE while CLOSED -> IGNORE
```

## 16. External movement

The gate may be operated outside HA:

- RF remote;
- local button;
- vendor app;
- intercom;
- another controller input.

Examples:

```text
CLOSED
closed_limit ON -> OFF
no local command
-> infer OPENING
```

```text
OPEN
open_limit ON -> OFF
no local command
-> infer CLOSING
```

If direction cannot be inferred:

```text
UNKNOWN_MOVING
```

should exist in the internal domain model.

## 17. Restore after restart

Persist:

```text
last_stable_state
last_direction
estimated_position
last_command
last_transition_timestamp
```

On restart:

1. inspect physical limit sensors;
2. use physical sensors as authority;
3. never resume movement automatically;
4. never restart a previous pulse/HOLD sequence;
5. if neither endpoint is known, restore cautiously to STOPPED/UNKNOWN according to available evidence.

## 18. Optional safety inputs

Future-ready model:

```text
photocell
obstacle
motor_running
power_available
```

MVP should at least allow:

- diagnostics;
- blocking CLOSE while a configured safety input is active.

Do not programmatically bypass physical safety systems.

## 19. Sensor conflict

If:

```text
open_limit = active
closed_limit = active
```

then:

```text
problem = LIMIT_SENSOR_CONFLICT
```

Default MVP behavior:

```text
block movement commands
```

until the conflict disappears.

Do not auto-move the gate to resolve it.

## 20. Source unavailable

If a required control entity is unavailable:

- reject the affected command;
- expose diagnostics;
- do not execute partial movement sequences.

If a non-critical diagnostic source is unavailable, the entire gate does not necessarily become unavailable.

## 21. Device Registry

Each Virtual Gate must create one HA Device.

Suggested metadata:

```text
manufacturer = Virtual Devices
model = Virtual Gate
```

All generated entities belong to that device.

## 22. Reconfigure

The user should be able to modify:

```text
name
control mode
source entities
limit sensors
active states
debounce
opening time
closing time
margins
pulse duration
hold duration
STOP strategy
direction-change strategy
repeated-command policy
safety behavior
```

Changing configuration must not unnecessarily change unique IDs.

## 23. Diagnostics entities

Recommended:

```text
sensor.<name>_detailed_state
sensor.<name>_last_direction
sensor.<name>_last_command
binary_sensor.<name>_problem
```

Some diagnostic entities may be disabled by default in Entity Registry.

## 24. Controller presets

Future presets:

```text
Generic Step-by-Step
Separate OPEN/CLOSE
Separate OPEN/CLOSE/STOP
Nice POA3/A style
Custom
```

Presets must only initialize strategies.

They must not prevent advanced overrides.
