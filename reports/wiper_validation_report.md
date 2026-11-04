# BCM Intermittent Wiper Function – Validation Report

## 1. Purpose

This report documents the verification results of the BCM intermittent wiper function.

The verification is based on CAN traces recorded during execution of the following test cases:

- TC-WIP-001 – Intermittent Wiper Activation
- TC-WIP-002 – Motor ON Until HOME
- TC-WIP-003 – Intermittent Delay
- TC-WIP-004 – OFF Request During Active Wiping

The CAN traces contain the transmitted CAN frames, timestamps, raw data and DBC-decoded signals.

---

## 2. Test Environment

The validation bench consists of:

- Python Test Environment
- BCM Simulator
- Wiper Motor Model
- python-can Virtual CAN Bus
- cantools DBC decoding
- CAN Trace Logger

Main CAN messages:

| CAN ID | Message | Sender |
|---|---|---|
| 0x100 | BCM_INPUTS | TestEnvironment |
| 0x101 | WIPER_FEEDBACK | WiperMotor |
| 0x200 | BCM_OUTPUTS | BCM |

The recorded traces are stored in:

```text
traces/
├── TC-WIP-001_trace.csv
├── TC-WIP-002_trace.csv
├── TC-WIP-003_trace.csv
└── TC-WIP-004_trace.csv
```

---

# 3. Requirement Verification

## 3.1 REQ-WIP-001 – Intermittent Activation

### Requirement

When:

- IgnitionStatus = ON
- WiperSwitch = INTERMITTENT
- WiperHomePosition = HOME

the BCM shall activate the wiper motor and enter the WIPING state.

### Expected Result

```text
WiperMotorCommand = ON
WiperStatus       = WIPING
```

### CAN Trace Evidence

From `TC-WIP-001_trace.csv`:

```text
0.008893  0x101  WIPER_FEEDBACK
WiperHomePosition=HOME

0.010456  0x100  BCM_INPUTS
IgnitionStatus=ON; WiperSwitch=INTERMITTENT

0.011031  0x200  BCM_OUTPUTS
WiperMotorCommand=ON; WiperStatus=WIPING

0.011812  0x101  WIPER_FEEDBACK
WiperHomePosition=NOT_HOME
```

The wiper was initially at HOME.

After the Test Environment requested INTERMITTENT operation, the BCM commanded the motor ON and changed its state to WIPING.

The motor model subsequently reported NOT_HOME, confirming that the wiping cycle started.

### Verdict

**PASS**

REQ-WIP-001 is satisfied.

---

## 3.2 REQ-WIP-002 – Motor ON Until HOME

### Requirement

During an active wiping cycle, the BCM shall keep the wiper motor ON until the wiper returns to the HOME position.

### Expected Behavior

```text
ON / WIPING
      ↓
NOT_HOME
      ↓
Motor remains ON
      ↓
HOME
      ↓
OFF / WAITING
```

The BCM must not command the motor OFF while the blade is NOT_HOME.

### CAN Trace Evidence

From `TC-WIP-002_trace.csv`:

```text
0.010371  0x200  BCM_OUTPUTS
WiperMotorCommand=ON; WiperStatus=WIPING

0.010988  0x101  WIPER_FEEDBACK
WiperHomePosition=NOT_HOME

1.524809  0x101  WIPER_FEEDBACK
WiperHomePosition=HOME

1.525511  0x200  BCM_OUTPUTS
WiperMotorCommand=OFF; WiperStatus=WAITING
```

No `WiperMotorCommand=OFF` frame was observed between the NOT_HOME feedback and the HOME feedback.

The BCM therefore maintained the motor command while the blade was outside the HOME position.

After HOME was received, the BCM commanded:

```text
WiperMotorCommand = OFF
WiperStatus       = WAITING
```

The measured BCM reaction after HOME was:

```text
1.525511 - 1.524809
= 0.000702 s
≈ 0.702 ms
```

No formal response-time requirement is defined for this value; it is included only as trace evidence.

### Verdict

**PASS**

REQ-WIP-002 is satisfied.

---

## 3.3 REQ-WIP-003 – Intermittent Delay

### Requirement

After completion of a wiping cycle, if INTERMITTENT remains selected, the BCM shall wait approximately 5 seconds before starting the next wiping cycle.

For this project, the accepted timing requirement is:

```text
5.0 s ± 0.1 s
```

Therefore:

```text
Minimum accepted delay = 4.900 s
Maximum accepted delay = 5.100 s
```

### Expected Behavior

```text
HOME
 ↓
OFF / WAITING
 ↓
5-second delay
 ↓
ON / WIPING
```

### CAN Trace Evidence

From `TC-WIP-003_trace.csv`:

```text
1.519059  0x101  WIPER_FEEDBACK
WiperHomePosition=HOME

1.519602  0x200  BCM_OUTPUTS
WiperMotorCommand=OFF; WiperStatus=WAITING

6.528791  0x200  BCM_OUTPUTS
WiperMotorCommand=ON; WiperStatus=WIPING

6.536369  0x101  WIPER_FEEDBACK
WiperHomePosition=NOT_HOME
```

### Timing Calculation

Beginning of intermittent waiting period:

```text
t_waiting = 1.519602 s
```

Beginning of the next wiping cycle:

```text
t_restart = 6.528791 s
```

Measured delay:

```text
6.528791 - 1.519602
= 5.009189 s
```

Comparison with requirement:

```text
Required range : 4.900 – 5.100 s
Measured value : 5.009189 s
```

The measured value is inside the accepted range.

### Verdict

**PASS**

REQ-WIP-003 is satisfied.

---

## 3.4 REQ-WIP-004 – OFF Request During Active Wiping

### Requirement

If the driver selects OFF while a wiping cycle is active and the blade is outside the HOME position, the BCM shall not stop the motor immediately.

The current wiping cycle shall be completed and the motor shall be stopped only after the blade returns HOME.

### Expected Behavior

```text
NOT_HOME
    ↓
Driver selects OFF
    ↓
Motor continues running
    ↓
HOME
    ↓
Motor OFF / PARKED
```

### CAN Trace Evidence

From `TC-WIP-004_trace.csv`:

```text
0.005478  0x101  WIPER_FEEDBACK
WiperHomePosition=NOT_HOME

0.006404  0x100  BCM_INPUTS
IgnitionStatus=ON; WiperSwitch=OFF

1.517642  0x101  WIPER_FEEDBACK
WiperHomePosition=HOME

1.518816  0x200  BCM_OUTPUTS
WiperMotorCommand=OFF; WiperStatus=PARKED
```

After the OFF request at:

```text
0.006404 s
```

no `WiperMotorCommand=OFF` frame was observed before the HOME feedback.

The blade returned HOME at:

```text
1.517642 s
```

Only afterward did the BCM transmit:

```text
WiperMotorCommand = OFF
WiperStatus       = PARKED
```

at:

```text
1.518816 s
```

### Timing Evidence

Time from OFF request until HOME:

```text
1.517642 - 0.006404
= 1.511238 s
```

BCM reaction after HOME:

```text
1.518816 - 1.517642
= 0.001174 s
≈ 1.17 ms
```

The important verification point is the event ordering:

```text
OFF request < HOME feedback < OFF/PARKED command
```

This ordering is confirmed by the CAN trace.

### Verdict

**PASS**

REQ-WIP-004 is satisfied.

---

# 4. Test Summary

| Test Case | Requirement | Verification | Result |
|---|---|---|---|
| TC-WIP-001 | REQ-WIP-001 | Intermittent mode activates wiping from HOME | PASS |
| TC-WIP-002 | REQ-WIP-002 | Motor remains ON until HOME | PASS |
| TC-WIP-003 | REQ-WIP-003 | Intermittent delay = 5.009 s | PASS |
| TC-WIP-004 | REQ-WIP-004 | OFF request completes current cycle before parking | PASS |

---

# 5. Conclusion

All four implemented requirements were successfully verified using the Python CAN validation bench.

The recorded CAN traces confirm that the BCM simulator:

- starts intermittent wiping correctly;
- maintains motor activation until the blade returns HOME;
- respects the defined intermittent delay;
- completes an active wiping cycle before parking when OFF is requested.

The CAN trace files provide the evidence used to support each PASS verdict.

## Final Result

```text
Requirements tested : 4
Passed              : 4
Failed              : 0

Overall Result: PASS
```

## Note

Because the test environment, BCM simulator and motor model execute in separate Python threads, the exact ordering of initial startup frames such as `OFF/PARKED` may vary slightly between executions.

The requirement verification is therefore based on the CAN transitions relevant to each individual test condition and expected result.