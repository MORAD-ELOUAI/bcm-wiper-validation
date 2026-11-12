from pathlib import Path
import sys
import threading
import time

import can
import cantools


# --------------------------------------------------
# Project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DBC_FILE = (
    PROJECT_ROOT
    / "dbc"
    / "bcm_wiper.dbc"
)

TRACE_FILE = (
    PROJECT_ROOT
    / "traces"
    / "TC-WIP-003_trace.csv"
)


# Allow imports from src/
sys.path.insert(
    0,
    str(PROJECT_ROOT / "src")
)


from bcm_simulator import run_bcm
from wiper_motor_model import run_wiper_motor
from can_trace_logger import run_can_logger


# --------------------------------------------------
# Load DBC
# --------------------------------------------------

db = cantools.database.load_file(DBC_FILE)

bcm_inputs = db.get_message_by_name(
    "BCM_INPUTS"
)

bcm_outputs = db.get_message_by_name(
    "BCM_OUTPUTS"
)


# --------------------------------------------------
# Requirement values
# --------------------------------------------------

EXPECTED_DELAY = 5.0
DELAY_TOLERANCE = 0.1


# --------------------------------------------------
# Test case
# --------------------------------------------------

def run_test():

    print("\nTC-WIP-003")
    print("INTERMITTENT WIPER DELAY")
    print("------------------------")


    # --------------------------------------------------
    # Reference timestamp for CAN trace
    # --------------------------------------------------

    test_start_time = time.monotonic()


    # --------------------------------------------------
    # Create Test Environment CAN node
    # --------------------------------------------------

    test_bus = can.Bus(
        interface="virtual",
        channel="wiper_network"
    )


    # --------------------------------------------------
    # Synchronization events
    # --------------------------------------------------

    bcm_ready = threading.Event()
    motor_ready = threading.Event()
    logger_ready = threading.Event()

    system_stop_event = threading.Event()
    logger_stop_event = threading.Event()


    # --------------------------------------------------
    # Create threads
    # --------------------------------------------------

    bcm_thread = threading.Thread(
        target=run_bcm,
        args=(
            bcm_ready,
            system_stop_event
        ),
        daemon=True
    )


    motor_thread = threading.Thread(
        target=run_wiper_motor,
        args=(
            motor_ready,
            system_stop_event
        ),
        daemon=True
    )


    logger_thread = threading.Thread(
        target=run_can_logger,
        args=(
            TRACE_FILE,
            test_start_time,
            logger_ready,
            logger_stop_event
        ),
        daemon=True
    )


    # --------------------------------------------------
    # Helper:
    # Send driver inputs
    # --------------------------------------------------

    def send_driver_inputs(
        ignition,
        wiper_switch
    ):

        input_signals = {
            "IgnitionStatus": ignition,
            "WiperSwitch": wiper_switch
        }


        payload = bcm_inputs.encode(
            input_signals
        )


        message = can.Message(
            arbitration_id=bcm_inputs.frame_id,
            data=payload,
            is_extended_id=False
        )


        test_bus.send(
            message
        )


        print(
            "\nTest Environment transmitted:"
        )

        print(
            f"IgnitionStatus = {ignition}"
        )

        print(
            f"WiperSwitch    = {wiper_switch}"
        )


    # --------------------------------------------------
    # Helper:
    # Wait for expected BCM output
    # --------------------------------------------------

    def wait_for_bcm_output(
        expected_motor,
        expected_status,
        timeout
    ):

        deadline = (
            time.monotonic()
            + timeout
        )


        while time.monotonic() < deadline:

            remaining_time = (
                deadline
                - time.monotonic()
            )


            rx_message = test_bus.recv(
                timeout=remaining_time
            )


            if rx_message is None:
                break


            # Ignore frames other than BCM_OUTPUTS
            if (
                rx_message.arbitration_id
                != bcm_outputs.frame_id
            ):
                continue


            output = bcm_outputs.decode(
                rx_message.data
            )


            motor = str(
                output["WiperMotorCommand"]
            )

            status = str(
                output["WiperStatus"]
            )


            print(
                "\nTest Environment observed BCM:"
            )

            print(
                f"WiperMotorCommand = {motor}"
            )

            print(
                f"WiperStatus       = {status}"
            )


            if (
                motor == expected_motor
                and status == expected_status
            ):

                timestamp = time.monotonic()

                return (
                    output,
                    timestamp
                )


        return (
            None,
            None
        )


    # --------------------------------------------------
    # Execute test
    # --------------------------------------------------

    try:

        # ==================================================
        # STEP 0
        # Start CAN Trace Logger
        # ==================================================

        logger_thread.start()


        if not logger_ready.wait(timeout=1.0):

            print("\nRESULT: FAIL")

            print(
                "Reason: CAN Trace Logger "
                "failed to start."
            )

            return False


        # ==================================================
        # STEP 1
        # Start BCM simulator
        # ==================================================

        print(
            "\nSTEP 1 - Start BCM simulator"
        )


        bcm_thread.start()


        if not bcm_ready.wait(timeout=1.0):

            print("\nRESULT: FAIL")

            print(
                "Reason: BCM simulator "
                "failed to start."
            )

            return False


        # ==================================================
        # STEP 2
        # Start Wiper Motor model
        # ==================================================

        print(
            "\nSTEP 2 - Start Wiper Motor model"
        )


        motor_thread.start()


        if not motor_ready.wait(timeout=1.0):

            print("\nRESULT: FAIL")

            print(
                "Reason: Wiper Motor model "
                "failed to start."
            )

            return False


        # ==================================================
        # STEP 3
        # Start intermittent wiping
        # ==================================================

        print(
            "\nSTEP 3 - Select INTERMITTENT mode"
        )


        send_driver_inputs(
            ignition="ON",
            wiper_switch="INTERMITTENT"
        )


        first_wipe, _ = wait_for_bcm_output(
            expected_motor="ON",
            expected_status="WIPING",
            timeout=2.0
        )


        if first_wipe is None:

            print("\nRESULT: FAIL")

            print(
                "Reason: BCM did not start "
                "the first wiping cycle."
            )

            return False


        # ==================================================
        # STEP 4
        # Wait for first cycle to complete
        #
        # Expected:
        #
        # MotorCommand = OFF
        # WiperStatus = WAITING
        # ==================================================

        print(
            "\nSTEP 4 - Wait for first cycle "
            "to complete"
        )


        waiting_output, t_waiting = (
            wait_for_bcm_output(
                expected_motor="OFF",
                expected_status="WAITING",
                timeout=3.0
            )
        )


        if waiting_output is None:

            print("\nRESULT: FAIL")

            print(
                "Reason: BCM did not enter "
                "OFF / WAITING after the "
                "first wiping cycle."
            )

            return False


        print(
            "\nIntermittent waiting period started."
        )


        # ==================================================
        # STEP 5
        # Wait for next wiping cycle
        #
        # Expected after approximately 5 seconds:
        #
        # MotorCommand = ON
        # WiperStatus = WIPING
        # ==================================================

        print(
            "\nSTEP 5 - Wait for next "
            "wiping cycle"
        )


        second_wipe, t_restart = (
            wait_for_bcm_output(
                expected_motor="ON",
                expected_status="WIPING",
                timeout=EXPECTED_DELAY + 2.0
            )
        )


        if second_wipe is None:

            print("\nRESULT: FAIL")

            print(
                "Reason: BCM did not restart "
                "the wiping cycle after the "
                "intermittent delay."
            )

            return False


        # ==================================================
        # STEP 6
        # Calculate measured delay
        # ==================================================

        measured_delay = (
            t_restart
            - t_waiting
        )


        minimum_delay = (
            EXPECTED_DELAY
            - DELAY_TOLERANCE
        )


        maximum_delay = (
            EXPECTED_DELAY
            + DELAY_TOLERANCE
        )


        print(
            "\nTiming measurement:"
        )


        print(
            f"WAITING started : "
            f"{t_waiting:.3f} s"
        )


        print(
            f"WIPING restarted: "
            f"{t_restart:.3f} s"
        )


        print(
            f"Measured delay  : "
            f"{measured_delay:.3f} s"
        )


        print(
            f"Expected delay  : "
            f"{EXPECTED_DELAY:.3f} "
            f"± {DELAY_TOLERANCE:.3f} s"
        )


        print(
            f"Accepted range  : "
            f"{minimum_delay:.3f} "
            f"to {maximum_delay:.3f} s"
        )


        # ==================================================
        # STEP 7
        # Test verdict
        # ==================================================

        if (
            minimum_delay
            <= measured_delay
            <= maximum_delay
        ):

            print(
                "\nRESULT: PASS"
            )


            print(
                "REQ-WIP-003 satisfied: "
                "the BCM waited the required "
                "intermittent delay before "
                "starting the next wiping cycle."
            )


            return True


        print(
            "\nRESULT: FAIL"
        )


        print(
            "Reason: Measured intermittent "
            "delay is outside the allowed "
            "tolerance."
        )


        return False


    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    finally:

        # --------------------------------------------------
        # Stop BCM and Wiper Motor first
        # --------------------------------------------------

        system_stop_event.set()


        if bcm_thread.is_alive():

            bcm_thread.join(
                timeout=1.0
            )


        if motor_thread.is_alive():

            motor_thread.join(
                timeout=1.0
            )


        # --------------------------------------------------
        # Stop logger last
        # --------------------------------------------------

        logger_stop_event.set()


        if logger_thread.is_alive():

            logger_thread.join(
                timeout=1.0
            )


        test_bus.shutdown()


        print(
            "\nTest Environment stopped."
        )


        print(
            f"\nCAN trace saved to:"
            f"\n{TRACE_FILE}"
        )


# --------------------------------------------------
# Standalone execution
# --------------------------------------------------

if __name__ == "__main__":

    success = run_test()

    sys.exit(
        0 if success else 1
    )