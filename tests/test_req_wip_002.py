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
    / "TC-WIP-002_trace.csv"
)


# Allow imports from src/
sys.path.insert(
    0,
    str(PROJECT_ROOT / "src")
)


from bcm_TheSimulator import run_bcm
from wiper_motor_model import run_wiper_motor
from can_trace_logger import run_can_logger


# --------------------------------------------------
# Load DBC
# --------------------------------------------------

db = cantools.database.load_file(DBC_FILE)

bcm_inputs = db.get_message_by_name(
    "BCM_INPUTS"
)

wiper_feedback = db.get_message_by_name(
    "WIPER_FEEDBACK"
)

bcm_outputs = db.get_message_by_name(
    "BCM_OUTPUTS"
)


# --------------------------------------------------
# Test case
# --------------------------------------------------

def run_test():

    print("\nTC-WIP-002")
    print("WIPER MOTOR REMAINS ON UNTIL HOME")
    print("---------------------------------")


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
    # Execute test
    # --------------------------------------------------

    try:

        # ==================================================
        # STEP 0
        # Start CAN logger
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
        # Start BCM
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
        # Request intermittent wiping
        # ==================================================

        print(
            "\nSTEP 3 - Select INTERMITTENT mode"
        )


        input_signals = {
            "IgnitionStatus": "ON",
            "WiperSwitch": "INTERMITTENT"
        }


        payload = bcm_inputs.encode(
            input_signals
        )


        tx_message = can.Message(
            arbitration_id=bcm_inputs.frame_id,
            data=payload,
            is_extended_id=False
        )


        test_bus.send(
            tx_message
        )


        print(
            "\nTest Environment transmitted:"
        )

        print(
            "IgnitionStatus = ON"
        )

        print(
            "WiperSwitch    = INTERMITTENT"
        )


        # ==================================================
        # STEP 4
        # Wait for BCM to start wiping
        # ==================================================

        print(
            "\nSTEP 4 - Wait for ON / WIPING"
        )


        deadline = (
            time.monotonic()
            + 2.0
        )


        wiping_started = False


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
                motor == "ON"
                and status == "WIPING"
            ):

                wiping_started = True

                break


        if not wiping_started:

            print("\nRESULT: FAIL")

            print(
                "Reason: BCM did not start "
                "the wiping cycle."
            )

            return False


        # ==================================================
        # STEP 5
        # Confirm blade leaves HOME
        # ==================================================

        print(
            "\nSTEP 5 - Wait for NOT_HOME"
        )


        deadline = (
            time.monotonic()
            + 2.0
        )


        not_home_received = False


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


            if (
                rx_message.arbitration_id
                != wiper_feedback.frame_id
            ):
                continue


            feedback = wiper_feedback.decode(
                rx_message.data
            )


            position = str(
                feedback["WiperHomePosition"]
            )


            print(
                "\nTest Environment observed feedback:"
            )

            print(
                f"WiperHomePosition = {position}"
            )


            if position == "NOT_HOME":

                not_home_received = True

                break


        if not not_home_received:

            print("\nRESULT: FAIL")

            print(
                "Reason: Wiper did not "
                "leave HOME."
            )

            return False


        # ==================================================
        # STEP 6
        # Monitor active wiping cycle
        #
        # Requirement:
        #
        # While blade is NOT_HOME:
        # Motor must remain ON.
        #
        # Motor OFF before HOME = FAIL.
        #
        # After HOME:
        # BCM should enter OFF / WAITING.
        # ==================================================

        print(
            "\nSTEP 6 - Verify motor remains ON "
            "until HOME"
        )


        home_received = False

        t_home = None
        t_waiting = None


        deadline = (
            time.monotonic()
            + 3.0
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


            # ------------------------------------------
            # Wiper feedback
            # ------------------------------------------

            if (
                rx_message.arbitration_id
                == wiper_feedback.frame_id
            ):

                feedback = wiper_feedback.decode(
                    rx_message.data
                )


                position = str(
                    feedback["WiperHomePosition"]
                )


                print(
                    "\nTest Environment observed feedback:"
                )

                print(
                    f"WiperHomePosition = {position}"
                )


                if (
                    position == "HOME"
                    and not home_received
                ):

                    home_received = True

                    t_home = time.monotonic()


                    print(
                        "\nHOME position reached."
                    )


            # ------------------------------------------
            # BCM output
            # ------------------------------------------

            elif (
                rx_message.arbitration_id
                == bcm_outputs.frame_id
            ):

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


                # --------------------------------------
                # FAIL:
                # BCM stopped motor before HOME
                # --------------------------------------

                if (
                    motor == "OFF"
                    and not home_received
                ):

                    print(
                        "\nRESULT: FAIL"
                    )

                    print(
                        "Reason: BCM stopped "
                        "the motor before the "
                        "wiper returned HOME."
                    )

                    return False


                # --------------------------------------
                # Correct completed cycle
                # --------------------------------------

                if (
                    motor == "OFF"
                    and status == "WAITING"
                    and home_received
                ):

                    t_waiting = time.monotonic()

                    break


                # --------------------------------------
                # FAIL:
                # Motor stopped after HOME,
                # but wrong state
                # --------------------------------------

                if (
                    motor == "OFF"
                    and home_received
                    and status != "WAITING"
                ):

                    print(
                        "\nRESULT: FAIL"
                    )

                    print(
                        "Reason: BCM stopped the "
                        "motor after HOME but did "
                        "not enter WAITING."
                    )

                    return False


        # ==================================================
        # STEP 7
        # Final verdict
        # ==================================================

        if not home_received:

            print("\nRESULT: FAIL")

            print(
                "Reason: HOME feedback "
                "was never received."
            )

            return False


        if t_waiting is None:

            print("\nRESULT: FAIL")

            print(
                "Reason: BCM did not enter "
                "OFF / WAITING after HOME."
            )

            return False


        # ==================================================
        # PASS
        # ==================================================

        print(
            "\nRESULT: PASS"
        )


        print(
            "REQ-WIP-002 satisfied: "
            "the BCM kept the wiper motor ON "
            "until the blade returned HOME."
        )


        print(
            "\nTiming evidence:"
        )


        print(
            f"HOME feedback received : "
            f"{t_home:.3f} s"
        )


        print(
            f"OFF/WAITING received   : "
            f"{t_waiting:.3f} s"
        )


        print(
            f"HOME -> OFF/WAITING    : "
            f"{t_waiting - t_home:.3f} s"
        )


        return True


    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    finally:

        # Stop BCM and motor first
        system_stop_event.set()


        if bcm_thread.is_alive():

            bcm_thread.join(
                timeout=1.0
            )


        if motor_thread.is_alive():

            motor_thread.join(
                timeout=1.0
            )


        # Stop logger last
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