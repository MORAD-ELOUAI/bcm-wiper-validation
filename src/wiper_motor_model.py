from pathlib import Path
import time

import can
import cantools


# --------------------------------------------------
# Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DBC_FILE = (
    PROJECT_ROOT
    / "dbc"
    / "bcm_wiper.dbc"
)


# Simplified plant-model assumption.
#
# This value represents the assumed physical duration
# of one complete:
#
# HOME -> NOT_HOME -> HOME
#
# wiping cycle.
#
# The BCM must NOT depend on this duration.
# It only reacts to WiperHomePosition feedback.
WIPER_CYCLE_TIME = 1.5


# --------------------------------------------------
# Load DBC
# --------------------------------------------------

db = cantools.database.load_file(
    DBC_FILE
)


wiper_feedback = db.get_message_by_name(
    "WIPER_FEEDBACK"
)


bcm_outputs = db.get_message_by_name(
    "BCM_OUTPUTS"
)


# --------------------------------------------------
# Wiper motor model
# --------------------------------------------------

def run_wiper_motor(
    ready_event=None,
    stop_event=None
):

    # --------------------------------------------------
    # Create CAN node for the simulated wiper motor
    # --------------------------------------------------

    motor_bus = can.Bus(
        interface="virtual",
        channel="wiper_network"
    )


    # --------------------------------------------------
    # Internal motor-model state
    # --------------------------------------------------

    # Latest motor command received from BCM.
    motor_command = "OFF"

    # Previous motor command.
    #
    # Used to detect:
    #
    # OFF -> ON
    # ON  -> OFF
    previous_motor_command = "OFF"


    # Simulated physical wiper position.
    wiper_position = "HOME"


    # True while one simulated wiping cycle
    # is physically in progress.
    cycle_active = False


    # Stores the time at which the current
    # simulated wiping cycle started.
    cycle_start_time = None


    # --------------------------------------------------
    # Helper function:
    # Send simulated park-position sensor feedback
    # --------------------------------------------------

    def send_feedback(position):

        payload = wiper_feedback.encode({
            "WiperHomePosition": position
        })


        message = can.Message(
            arbitration_id=wiper_feedback.frame_id,
            data=payload,
            is_extended_id=False
        )


        motor_bus.send(message)


        print("\nWiperMotor transmitted:")
        print(
            f"WiperHomePosition = {position}"
        )


    # --------------------------------------------------
    # Initial physical position
    # --------------------------------------------------

    # The motor/plant model owns the physical
    # WiperHomePosition signal.
    #
    # At startup we assume that the wiper
    # is physically parked at HOME.
    send_feedback(
        wiper_position
    )


    print(
        "\nWiper motor model started..."
    )


    # Inform the test that:
    #
    # - the motor CAN node exists
    # - initial HOME feedback was transmitted
    #
    # The BCM should therefore be started before
    # the motor model.
    if ready_event is not None:
        ready_event.set()


    # --------------------------------------------------
    # Main motor-model loop
    # --------------------------------------------------

    try:

        while True:


            # --------------------------------------------------
            # Stop motor model when requested by test
            # --------------------------------------------------

            if (
                stop_event is not None
                and stop_event.is_set()
            ):
                break


            # --------------------------------------------------
            # Receive BCM outputs
            # --------------------------------------------------

            rx_message = motor_bus.recv(
                timeout=0.01
            )


            if (
                rx_message is not None
                and rx_message.arbitration_id
                == bcm_outputs.frame_id
            ):

                signals = bcm_outputs.decode(
                    rx_message.data
                )


                motor_command = str(
                    signals[
                        "WiperMotorCommand"
                    ]
                )


                # WiperStatus is not required by the
                # physical motor model, but decoding it
                # is useful for traces/debugging.
                wiper_status = str(
                    signals[
                        "WiperStatus"
                    ]
                )


                print(
                    "\nWiperMotor received:"
                )

                print(
                    f"WiperMotorCommand = "
                    f"{motor_command}"
                )

                print(
                    f"WiperStatus       = "
                    f"{wiper_status}"
                )


                # --------------------------------------------------
                # Detect OFF -> ON
                #
                # BCM has started the motor.
                # --------------------------------------------------

                if (
                    previous_motor_command == "OFF"
                    and motor_command == "ON"
                ):


                    # Normal case:
                    #
                    # A new wiping cycle should start
                    # while the blade is parked at HOME.
                    if wiper_position == "HOME":

                        print(
                            "\nWiperMotor: "
                            "new wiping cycle started"
                        )


                        cycle_active = True

                        cycle_start_time = (
                            time.monotonic()
                        )


                        # Simplified physical behavior:
                        #
                        # Once the motor starts, the
                        # blade immediately leaves the
                        # HOME position.
                        wiper_position = (
                            "NOT_HOME"
                        )


                        send_feedback(
                            wiper_position
                        )


                    # Abnormal case:
                    #
                    # BCM starts the motor while the
                    # blade is already outside HOME.
                    else:

                        print(
                            "\nWiperMotor WARNING: "
                            "motor activated while "
                            "wiper is NOT_HOME"
                        )


                # --------------------------------------------------
                # Detect ON -> OFF while cycle is active
                #
                # This represents a BCM defect:
                #
                # motor power was removed before the
                # wiper reached HOME.
                # --------------------------------------------------

                elif (
                    previous_motor_command == "ON"
                    and motor_command == "OFF"
                    and cycle_active
                ):

                    print(
                        "\nWiperMotor WARNING: "
                        "motor stopped before "
                        "wiper reached HOME"
                    )


                    # Stop simulated physical movement.
                    cycle_active = False

                    cycle_start_time = None


                    # IMPORTANT:
                    #
                    # Do NOT send HOME.
                    #
                    # The blade remains physically
                    # outside its park position.
                    #
                    # Therefore:
                    #
                    # wiper_position remains NOT_HOME.


                # --------------------------------------------------
                # Store current command for next
                # OFF -> ON / ON -> OFF comparison
                # --------------------------------------------------

                previous_motor_command = (
                    motor_command
                )


            # --------------------------------------------------
            # Simulate physical wiping movement
            # --------------------------------------------------

            if (
                cycle_active
                and motor_command == "ON"
                and cycle_start_time is not None
            ):

                elapsed_time = (
                    time.monotonic()
                    - cycle_start_time
                )


                # --------------------------------------------------
                # Complete one simulated physical cycle
                # --------------------------------------------------

                if (
                    elapsed_time
                    >= WIPER_CYCLE_TIME
                ):

                    # Blade has returned to its
                    # physical park position.
                    wiper_position = "HOME"


                    # Simulate park-position sensor
                    # changing back to HOME.
                    send_feedback(
                        wiper_position
                    )


                    # Physical cycle is now complete.
                    cycle_active = False

                    cycle_start_time = None


                    print(
                        "\nWiperMotor: "
                        "wiping cycle completed"
                    )


    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    finally:

        motor_bus.shutdown()

        print(
            "\nWiper motor model stopped."
        )


# --------------------------------------------------
# Standalone execution
# --------------------------------------------------

if __name__ == "__main__":

    run_wiper_motor()