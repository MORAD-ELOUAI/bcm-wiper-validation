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
DBC_FILE = PROJECT_ROOT / "dbc" / "bcm_wiper.dbc"
TRACE_FILE = (
    PROJECT_ROOT
    / "traces"
    / "TC-WIP-004_trace.csv"
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bcm_simulator import run_bcm
from wiper_motor_model import run_wiper_motor
from can_trace_logger import run_can_logger


# --------------------------------------------------
# Load DBC
# --------------------------------------------------

db = cantools.database.load_file(DBC_FILE)

bcm_inputs = db.get_message_by_name("BCM_INPUTS")
wiper_feedback = db.get_message_by_name("WIPER_FEEDBACK")
bcm_outputs = db.get_message_by_name("BCM_OUTPUTS")


# --------------------------------------------------
# Test case
# --------------------------------------------------

def run_test():

    print("\nTC-WIP-004")
    print("SWITCH OFF DURING ACTIVE WIPING")
    print("--------------------------------")


    # --------------------------------------------------
    # Create Test Environment CAN node
    # --------------------------------------------------

    test_bus = can.Bus(
        interface="virtual",
        channel="wiper_network"
    )


    # --------------------------------------------------
    # Thread synchronization
    # --------------------------------------------------

    bcm_ready = threading.Event()
    motor_ready = threading.Event()
    system_stop_event = threading.Event()
    logger_stop_event = threading.Event()
    logger_ready = threading.Event()


    test_start_time = time.monotonic()


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
    # Create BCM thread
    # --------------------------------------------------

    bcm_thread = threading.Thread(
        target=run_bcm,
        args=(bcm_ready, system_stop_event),
        daemon=True
    )


    # --------------------------------------------------
    # Create Wiper Motor thread
    # --------------------------------------------------

    motor_thread = threading.Thread(
        target=run_wiper_motor,
        args=(motor_ready, system_stop_event),
        daemon=True
    )


    # --------------------------------------------------
    # Helper:
    # Send driver inputs
    # --------------------------------------------------

    def send_driver_inputs(ignition, wiper_switch):

        input_signals = {
            "IgnitionStatus": ignition,
            "WiperSwitch": wiper_switch
        }

        payload = bcm_inputs.encode(input_signals)

        message = can.Message(
            arbitration_id=bcm_inputs.frame_id,
            data=payload,
            is_extended_id=False
        )

        test_bus.send(message)

        timestamp = time.monotonic()

        print("\nTest Environment transmitted:")
        print(f"IgnitionStatus = {ignition}")
        print(f"WiperSwitch    = {wiper_switch}")

        return timestamp


    # --------------------------------------------------
    # Helper:
    # Wait for expected BCM output
    # --------------------------------------------------

    def wait_for_bcm_output(
        expected_motor,
        expected_status,
        timeout
    ):

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:

            remaining_time = (
                deadline - time.monotonic()
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

            signals = bcm_outputs.decode(
                rx_message.data
            )

            actual_motor = str(
                signals["WiperMotorCommand"]
            )

            actual_status = str(
                signals["WiperStatus"]
            )

            print("\nTest Environment observed BCM:")
            print(
                f"WiperMotorCommand = {actual_motor}"
            )
            print(
                f"WiperStatus       = {actual_status}"
            )

            if (
                actual_motor == expected_motor
                and actual_status == expected_status
            ):
                timestamp = time.monotonic()

                return (
                    signals,
                    timestamp
                )

        return (
            None,
            None
        )


    # --------------------------------------------------
    # Helper:
    # Wait for expected Wiper Feedback
    # --------------------------------------------------

    def wait_for_wiper_feedback(
        expected_position,
        timeout
    ):

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:

            remaining_time = (
                deadline - time.monotonic()
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

            signals = wiper_feedback.decode(
                rx_message.data
            )

            position = str(
                signals["WiperHomePosition"]
            )

            print(
                "\nTest Environment observed feedback:"
            )

            print(
                f"WiperHomePosition = {position}"
            )

            if position == expected_position:

                timestamp = time.monotonic()

                return (
                    signals,
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
        # STEP 1
        # Start BCM simulator
        # ==================================================

        logger_thread.start()

        if not logger_ready.wait(timeout=1.0):

         print("\nRESULT: FAIL")

         print(
         "Reason: CAN Trace Logger "
         "failed to start."
         )

         return False



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


        # Wait for BCM to start wiping
        first_wipe, _ = wait_for_bcm_output(
            expected_motor="ON",
            expected_status="WIPING",
            timeout=2.0
        )

        if first_wipe is None:

            print("\nRESULT: FAIL")

            print(
                "Reason: BCM did not start "
                "the wiping cycle."
            )

            return False


        # ==================================================
        # STEP 4
        # Confirm blade has left HOME
        # ==================================================

        print(
            "\nSTEP 4 - Wait for NOT_HOME"
        )

        not_home_feedback, _ = (
            wait_for_wiper_feedback(
                expected_position="NOT_HOME",
                timeout=2.0
            )
        )

        if not_home_feedback is None:

            print("\nRESULT: FAIL")

            print(
                "Reason: Wiper did not "
                "leave HOME."
            )

            return False

        print(
            "\nWiper is NOT_HOME."
        )


        # ==================================================
        # STEP 5
        # Driver selects OFF during active wiping
        # ==================================================

        print(
            "\nSTEP 5 - Driver selects OFF "
            "while wiper is NOT_HOME"
        )

        t1 = send_driver_inputs(
            ignition="ON",
            wiper_switch="OFF"
        )


        # ==================================================
        # STEP 6
        # Monitor sequence after OFF request
        #
        # Required sequence:
        #
        # OFF request
        #     ↓
        # HOME feedback
        #     ↓
        # OFF / PARKED
        #
        # Motor OFF before HOME = FAIL
        # ==================================================

        print(
            "\nSTEP 6 - Monitor completion "
            "of current wiping cycle"
        )

        home_received = False

        t2 = None
        t3 = None

        deadline = time.monotonic() + 3.0


        while time.monotonic() < deadline:

            remaining_time = (
                deadline - time.monotonic()
            )

            rx_message = test_bus.recv(
                timeout=remaining_time
            )

            if rx_message is None:
                break


            # ------------------------------------------
            # Wiper physical feedback
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

                    t2 = time.monotonic()

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
                # Motor stopped before HOME
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
                        "the motor before HOME "
                        "was reached."
                    )

                    return False


                # --------------------------------------
                # PASS candidate:
                # HOME was reached first,
                # then BCM entered OFF / PARKED
                # --------------------------------------

                if (
                    motor == "OFF"
                    and status == "PARKED"
                    and home_received
                ):

                    t3 = time.monotonic()

                    break


                # --------------------------------------
                # FAIL:
                # Motor stopped after HOME,
                # but state is not PARKED
                # --------------------------------------

                if (
                    motor == "OFF"
                    and home_received
                    and status != "PARKED"
                ):

                    print(
                        "\nRESULT: FAIL"
                    )

                    print(
                        "Reason: Motor was stopped "
                        "after HOME, but BCM did not "
                        "enter PARKED."
                    )

                    return False


        # ==================================================
        # STEP 7
        # Final validation
        # ==================================================

        if not home_received:

            print(
                "\nRESULT: FAIL"
            )

            print(
                "Reason: HOME feedback "
                "was never received."
            )

            return False


        if t3 is None:

            print(
                "\nRESULT: FAIL"
            )

            print(
                "Reason: BCM did not command "
                "OFF / PARKED after HOME."
            )

            return False


        # ==================================================
        # PASS
        # ==================================================

        print(
            "\nRESULT: PASS"
        )

        print(
            "REQ-WIP-004 satisfied: "
            "the current wiping cycle "
            "completed before the BCM "
            "stopped the motor."
        )


        # --------------------------------------------------
        # Test evidence
        # --------------------------------------------------

        print(
            "\nEvent timestamps:"
        )

        print(
            f"OFF request sent       : "
            f"{t1:.3f} s"
        )

        print(
            f"HOME feedback received : "
            f"{t2:.3f} s"
        )

        print(
            f"OFF/PARKED received    : "
            f"{t3:.3f} s"
        )


        print(
            "\nRelative timing:"
        )

        print(
            f"OFF -> HOME          : "
            f"{t2 - t1:.3f} s"
        )

        print(
            f"HOME -> OFF/PARKED   : "
            f"{t3 - t2:.3f} s"
        )


        return True


    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    finally:

        system_stop_event.set()


        if bcm_thread.is_alive():

            bcm_thread.join(
                timeout=1.0
            )


        if motor_thread.is_alive():

            motor_thread.join(
                timeout=1.0
            )




        # Stop logger only after producers have stopped
        logger_stop_event.set()


        if logger_thread.is_alive():

           logger_thread.join(
            timeout=1.0)
            


        test_bus.shutdown()


        print(
            "\nTest Environment stopped."
        )

        print(
            f"\nCAN trace saved to:"
            f"\n{TRACE_FILE}")


# --------------------------------------------------
# Standalone execution
# --------------------------------------------------

if __name__ == "__main__":

    success = run_test()

    sys.exit(
        0 if success else 1
    )