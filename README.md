# BCM Intermittent Wiper Function – CAN-Based ECU Validation Bench

## Overview

This project implements a software-based CAN ECU verification bench for the intermittent wiper function of a simulated Body Control Module (BCM). It reproduces a simplified requirement-driven automotive test workflow using Python, DBC-based CAN communication, a plant model, automated test cases, and trace-based verification.

The goal is to verify BCM behavior against defined requirements using:

- Python
- python-can
- cantools
- CAN DBC communication
- Virtual CAN communication
- Requirement-based test cases
- CAN trace logging
- Trace-based verification

The project simulates three main CAN nodes:

- Test Environment
- BCM
- Wiper Motor Model

A passive CAN Trace Logger records the communication during test execution.

---

## System Architecture

```                    Virtual CAN Bus
       ┌──────────────┬──────────────┬──────────────┐
       │              │              │              │
       ▼              ▼              ▼              ▼
Test Environment     BCM       Wiper Motor     Trace Logger
                                Model            (passive)
                                                   │
                                                   ▼
                                              CSV Traces
```

The Test Environment sends driver input stimuli and evaluates the observed BCM behavior.

The BCM processes the inputs and controls the wiper motor.

The Wiper Motor Model simulates the physical blade position and sends HOME / NOT_HOME feedback. If the BCM removes the motor command before the simulated blade reaches HOME, the model does not generate false HOME feedback, allowing premature motor shutdown defects to be detected.

The CAN Trace Logger passively records all CAN communication.

---

## CAN Messages

### BCM_INPUTS

CAN ID:

```text
0x100
```

Sender:

```text
TestEnvironment
```

Signals:

- IgnitionStatus
- WiperSwitch

---

### WIPER_FEEDBACK

CAN ID:

```text
0x101
```

Sender:

```text
WiperMotor
```

Signals:

- WiperHomePosition

---

### BCM_OUTPUTS

CAN ID:

```text
0x200
```

Sender:

```text
BCM
```

Signals:

- WiperMotorCommand
- WiperStatus

---

## BCM States

The simplified BCM wiper logic uses three main states:

```text
PARKED
WIPING
WAITING
```

Typical intermittent operation:

```text
PARKED
   |
   | INTERMITTENT selected
   v
WIPING
   |
   | blade returns HOME
   v
WAITING
   |
   | 5-second delay
   v
WIPING
```

---

## Requirements

### REQ-WIP-001

When ignition is ON, INTERMITTENT mode is selected and the blade is at HOME, the BCM shall start a wiping cycle.

Expected output:

```text
WiperMotorCommand = ON
WiperStatus = WIPING
```

### REQ-WIP-002

During a wiping cycle, the BCM shall keep the motor ON until the blade returns HOME.

### REQ-WIP-003

After completing a wiping cycle while INTERMITTENT remains selected, the BCM shall wait:

```text
5.0 ± 0.1 seconds
```

before starting the next cycle.

### REQ-WIP-004

If the driver selects OFF during an active wiping cycle, the BCM shall complete the current cycle before stopping the motor.

The motor shall only be stopped after HOME is reached.

---

## Test Cases

| Test Case | Requirement | Description | Result |
|---|---|---|---|
| TC-WIP-001 | REQ-WIP-001 | Intermittent activation | PASS |
| TC-WIP-002 | REQ-WIP-002 | Motor remains ON until HOME | PASS |
| TC-WIP-003 | REQ-WIP-003 | 5-second intermittent delay | PASS |
| TC-WIP-004 | REQ-WIP-004 | OFF during active wiping | PASS |

---

## CAN Trace Logging

Each test generates a CSV trace containing:

- Relative timestamp
- CAN ID
- Message name
- Sender
- DLC
- Raw CAN payload
- Decoded signals

Example:

```text
Time_s,CAN_ID,Message,Sender,DLC,Data,Decoded_Signals
0.004952,0x200,BCM_OUTPUTS,BCM,8,03 00 00 00 00 00 00 00,WiperMotorCommand=ON; WiperStatus=WIPING
```

Trace files:

```text
traces/
├── TC-WIP-001_trace.csv
├── TC-WIP-002_trace.csv
├── TC-WIP-003_trace.csv
└── TC-WIP-004_trace.csv
```

---

## Project Structure

bcm_wiper_validation/
│
├── README.md
├── requirements.txt
│
├── dbc/
│   └── bcm_wiper.dbc
│
├── requirements/
│   └── wiper_requirements.md
│
├── src/
│   ├── bcm_simulator.py
│   ├── wiper_motor_model.py
│   └── can_trace_logger.py
│
├── tests/
│   ├── test_req_wip_001.py
│   ├── test_req_wip_002.py
│   ├── test_req_wip_003.py
│   └── test_req_wip_004.py
│
├── traces/
│   ├── TC-WIP-001_trace.csv
│   ├── TC-WIP-002_trace.csv
│   ├── TC-WIP-003_trace.csv
│   └── TC-WIP-004_trace.csv
│
└── reports/
    └── wiper_validation_report.md
```

---

## Tools and Libraries

- Python 3.11
- python-can
- cantools
- Python standard libraries: threading, pathlib, csv, time

---

## Running a Test

Activate the Python virtual environment:

```powershell
.venv\Scripts\activate
```

Run a test:

```powershell
python tests\test_req_wip_001.py
```

Example for TC-WIP-004:

```powershell
python tests\test_req_wip_004.py
```

After execution, the corresponding CAN trace is generated automatically in the `traces` directory.

---

## Verification Approach

The requirement verification flow used in this project is:

```text
Requirement
    ↓
Test Case
    ↓
Test Execution
    ↓
CAN Trace
    ↓
Expected vs Actual Comparison
    ↓
PASS / FAIL
```

The CAN traces provide the evidence used to verify the implementation against the defined requirements.

---

## Result

All four implemented requirements were successfully verified.

```text
Requirements tested : 4
Passed              : 4
Failed              : 0

Overall Result: PASS
```

---

## Scope

This project uses a software-based virtual CAN network and simplified BCM and motor models.

It is intended as a learning and portfolio project demonstrating automotive ECU verification and validation concepts such as:

- CAN communication
- DBC usage
- requirement-based testing
- ECU simulation
- plant modeling
- timing verification
- CAN trace analysis
- requirement traceability

For detailed requirement verification and CAN trace evidence, see:

`reports/wiper_validation_report.md`