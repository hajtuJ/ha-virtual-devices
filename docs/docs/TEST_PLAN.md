# Test Plan

## 1. Testing philosophy

The highest-risk code is:

```text
state machine
command sequencing
timing
restore behavior
```

These require strong automated tests.

## 2. State machine unit tests

### Normal flow

```text
CLOSED + OPEN -> OPENING
OPENING + OPEN_LIMIT_ON -> OPEN
OPEN + CLOSE -> CLOSING
CLOSING + CLOSED_LIMIT_ON -> CLOSED
```

### Direction memory

```text
OPENING + STOP
-> STOPPED
-> last_direction=OPENING
```

```text
CLOSING + STOP
-> STOPPED
-> last_direction=CLOSING
```

### Direction reversal

Test configured strategies for:

```text
OPENING + CLOSE
CLOSING + OPEN
```

### Repeated commands

Test:

```text
IGNORE
REPEAT
STOP
CUSTOM_SEQUENCE
```

where implemented.

### No limits

Travel time may complete movement.

### With limits

Timeout must create fault and must not fake endpoint state.

### Conflicting limits

```text
OPEN_LIMIT=ON
CLOSED_LIMIT=ON
-> LIMIT_SENSOR_CONFLICT
```

### External movement

```text
CLOSED
CLOSED_LIMIT ON -> OFF
without local command
-> OPENING
```

and equivalent from OPEN.

### Restore

Test:

- CLOSED;
- OPEN;
- STOPPED + last_direction;
- restart during previous movement;
- physical limit overrides restored state;
- both limits conflict.

## 3. Position tests

Opening:

```text
0 -> ~50 after half opening_time
```

Closing:

```text
100 -> ~50 after half closing_time
```

STOP freezes position.

Physical limit recalibrates to 0/100.

## 4. Command executor

### Pulse

Expected:

```text
activate
wait
deactivate
```

### Hold

Expected:

```text
activate
wait
deactivate
```

with distinct semantic configuration.

### Cleanup on cancellation

Critical test:

- start pulse/HOLD;
- cancel task;
- confirm deactivate is called.

### Serialization

Parallel OPEN/CLOSE requests must not execute unsafe overlapping activations.

### Minimum interval

Verify configured interval.

### Unavailable source

Command is rejected before unsafe partial execution.

## 5. Home Assistant tests

Use current recommended custom component test helpers.

### Config Flow

Test:

- create Virtual Gate;
- control mode selection;
- 0/1/2 limits;
- invalid durations;
- invalid source combinations;
- STOP unsupported;
- translations.

### Cover entity

Verify:

```text
device_class
supported features
availability
open delegation
close delegation
stop delegation
```

### Device Registry

Verify:

- one gate => one device;
- multiple gates => distinct devices;
- entities assigned correctly.

### Listener lifecycle

Verify:

- sensor change updates gate;
- unload removes listeners;
- reload does not duplicate listeners.

### Reconfigure

Verify:

- configuration updates;
- stable unique_id;
- no duplicate device;
- source listeners are replaced correctly.

## 6. Safety regression tests

Must never happen:

1. HA startup causes movement.
2. reload causes movement.
3. sensor conflict causes automatic motion.
4. cancelled HOLD leaves relay active.
5. unsupported STOP is advertised.
6. timeout with endpoint sensor marks endpoint reached.
7. OPEN and CLOSE relays remain active simultaneously accidentally.
8. partial sequence continues after critical source becomes unavailable.
