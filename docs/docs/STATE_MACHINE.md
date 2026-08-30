# Virtual Gate — State Machine

## 1. Domain states

```text
UNKNOWN
CLOSED
OPENING
OPEN
CLOSING
STOPPED
UNKNOWN_MOVING
ERROR
```

## 2. Direction

```text
UNKNOWN
OPENING
CLOSING
```

Store:

```text
current_direction
last_direction
```

On STOP:

```text
state = STOPPED
current_direction = UNKNOWN
last_direction = previous current_direction
```

Never clear `last_direction` merely because the gate stopped.

## 3. Core domain events

```text
COMMAND_OPEN
COMMAND_CLOSE
COMMAND_STOP

OPEN_LIMIT_ON
OPEN_LIMIT_OFF

CLOSED_LIMIT_ON
CLOSED_LIMIT_OFF

MOVEMENT_TIMER_TICK
MOVEMENT_TIMEOUT

SOURCE_AVAILABLE
SOURCE_UNAVAILABLE

OBSTACLE_ON
OBSTACLE_OFF

RESTORE
CONFIG_CHANGED
```

## 4. CLOSED

```text
COMMAND_OPEN
-> execute OPEN strategy
-> OPENING
-> current_direction=OPENING
-> last_direction=OPENING
```

External movement:

```text
CLOSED_LIMIT_OFF
without local movement command
-> OPENING
-> last_direction=OPENING
```

## 5. OPEN

```text
COMMAND_CLOSE
-> execute CLOSE strategy
-> CLOSING
-> current_direction=CLOSING
-> last_direction=CLOSING
```

External movement:

```text
OPEN_LIMIT_OFF
without local movement command
-> CLOSING
-> last_direction=CLOSING
```

## 6. OPENING

```text
OPEN_LIMIT_ON
-> OPEN
-> position=100
-> current_direction=UNKNOWN
```

```text
COMMAND_STOP
-> execute configured STOP strategy
-> STOPPED
-> last_direction=OPENING
```

```text
COMMAND_CLOSE
-> execute configured direction-change strategy
-> CLOSING
-> last_direction=CLOSING
```

Timeout with OPEN limit configured:

```text
-> problem=OPENING_TIMEOUT
-> do not claim OPEN
```

Timeout without OPEN limit:

```text
-> OPEN
-> position=100
```

## 7. CLOSING

```text
CLOSED_LIMIT_ON
-> CLOSED
-> position=0
-> current_direction=UNKNOWN
```

```text
COMMAND_STOP
-> execute configured STOP strategy
-> STOPPED
-> last_direction=CLOSING
```

```text
COMMAND_OPEN
-> execute configured direction-change strategy
-> OPENING
-> last_direction=OPENING
```

Timeout with CLOSED limit configured:

```text
-> problem=CLOSING_TIMEOUT
-> do not claim CLOSED
```

Timeout without CLOSED limit:

```text
-> CLOSED
-> position=0
```

## 8. STOPPED

STOPPED is not enough to determine the next physical command for step-by-step controllers.

Example:

```text
state = STOPPED
last_direction = OPENING
```

A subsequent CLOSE command may require a different physical sequence than when:

```text
state = STOPPED
last_direction = CLOSING
```

Strategies must receive both current state and last direction.

## 9. Sensor priority

Physical endpoint sensors override time estimation.

```text
CLOSED_LIMIT_ON
-> CLOSED
-> position=0
```

```text
OPEN_LIMIT_ON
-> OPEN
-> position=100
```

unless both are active.

## 10. Conflict

```text
OPEN_LIMIT_ON && CLOSED_LIMIT_ON
```

results in:

```text
problem=LIMIT_SENSOR_CONFLICT
```

Default behavior:

```text
block motion commands
```

No automatic movement is allowed.

## 11. Position estimation

Opening:

```text
position =
start_position +
elapsed_ms / opening_time_ms * 100
```

Closing:

```text
position =
start_position -
elapsed_ms / closing_time_ms * 100
```

Clamp to:

```text
0..100
```

Freeze on STOP.

Correct to endpoint value when a physical limit activates.

## 12. Command serialization

Exactly one physical command sequence may execute at a time.

Use a lock / serialized executor.

Incoming commands while a sequence is executing must follow an explicit policy.

Never permit accidental simultaneous activation of mutually exclusive OPEN/CLOSE relays.

## 13. Minimum intervals

Support:

```text
minimum_command_interval_ms
direction_change_delay_ms
pulse_interval_ms
```

## 14. Restore

On HA startup/reload:

1. inspect endpoint sensors;
2. CLOSED limit -> CLOSED;
3. OPEN limit -> OPEN;
4. both -> conflict;
5. neither -> cautiously restore context;
6. do not restart old timers as active motion;
7. do not execute any physical action automatically.

## 15. Mapping to HA cover state

Suggested mapping:

```text
CLOSED         -> closed
OPEN           -> open
OPENING        -> opening
CLOSING        -> closing
STOPPED        -> open + detailed_state=stopped
UNKNOWN        -> unknown
UNKNOWN_MOVING -> unknown or best safe supported mapping
ERROR          -> mapped from physical evidence + diagnostic problem
```

Verify the current Home Assistant `CoverEntity` behavior before final implementation.

## 16. Invariants

1. CLOSED => position=0 when known.
2. OPEN => position=100 when known.
3. OPENING => current_direction=OPENING.
4. CLOSING => current_direction=CLOSING.
5. STOPPED => current_direction=UNKNOWN.
6. STOPPED preserves last_direction.
7. both endpoint sensors active => conflict.
8. endpoint timeout with a configured sensor does not fake endpoint success.
9. HA restart never starts movement.
10. unsupported STOP is not exposed as supported.
11. cancellation of pulse/HOLD must deactivate source control.
