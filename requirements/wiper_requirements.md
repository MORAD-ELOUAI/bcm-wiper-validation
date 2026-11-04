# BCM Intermittent Wiper Requirements


## REQ-WIP-001 — Intermittent Activation

Given:

- IgnitionStatus = ON
- WiperSwitch = INTERMITTENT
- WiperHomePosition = HOME

The BCM shall command:

- WiperMotorCommand = ON
- WiperStatus = WIPING


## REQ-WIP-002 — Motor ON Until HOME

During an active wiping cycle, the BCM shall maintain:

- WiperMotorCommand = ON

while:

- WiperHomePosition = NOT_HOME

The BCM shall stop the motor only after the wiper returns HOME.


## REQ-WIP-003 — Intermittent Delay

After a wiping cycle is completed and:

- WiperSwitch remains INTERMITTENT
- WiperHomePosition = HOME

the BCM shall enter the WAITING state.

The BCM shall wait:

5.0 ± 0.1 seconds

before starting the next wiping cycle.


## REQ-WIP-004 — OFF Request During Active Wiping

If:

- the wiper is currently WIPING
- WiperHomePosition = NOT_HOME
- the driver changes WiperSwitch to OFF

the BCM shall keep:

- WiperMotorCommand = ON

until the blade returns HOME.

After HOME is reached, the BCM shall command:

- WiperMotorCommand = OFF
- WiperStatus = PARKED


# Requirement Traceability

| Requirement | Test Case | CAN Trace | Result |
|---|---|---|---|
| REQ-WIP-001 | TC-WIP-001 | TC-WIP-001_trace.csv | PASS |
| REQ-WIP-002 | TC-WIP-002 | TC-WIP-002_trace.csv | PASS |
| REQ-WIP-003 | TC-WIP-003 | TC-WIP-003_trace.csv | PASS |
| REQ-WIP-004 | TC-WIP-004 | TC-WIP-004_trace.csv | PASS |