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

INTERMITTENT_DELAY = 5.0


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
# BCM simulator
# --------------------------------------------------

def run_bcm(
    ready_event=None,
    stop_event=None
):

    # --------------------------------------------------
    # Create BCM CAN node
    # --------------------------------------------------

    bcm_bus = can.Bus(
        interface="virtual",
        channel="wiper_network"
    )


    # --------------------------------------------------
    # Latest external inputs
    # --------------------------------------------------

    ignition = "OFF"
    wiper_switch = "OFF"

    # Physical wiper position is owned by
    # the Wiper Motor model.
    home_position = None


    # --------------------------------------------------
    # Internal BCM state
    # --------------------------------------------------

    wiper_state = "PARKED"

    motor_command = "OFF"

    # Remembers whether the blade has left HOME
    # during the current wiping cycle.
    has_left_home = False

    # Used for REQ-WIP-003 intermittent delay.
    wait_start_time = None


    # --------------------------------------------------
    # Last transmitted BCM output
    #
    # BCM_OUTPUTS is event-driven:
    # transmit only when output changes.
    # --------------------------------------------------

    last_transmitted_output = None


    # --------------------------------------------------
    # Helper:
    # Transmit BCM output when it changes
    # --------------------------------------------------

    def transmit_output():

        nonlocal last_transmitted_output

        current_output = (
            motor_command,
            wiper_state
        )

        if (
            current_output
            == last_transmitted_output
        ):
            return


        payload = bcm_outputs.encode({
            "WiperMotorCommand": motor_command,
            "WiperStatus": wiper_state
        })


        message = can.Message(
            arbitration_id=bcm_outputs.frame_id,
            data=payload,
            is_extended_id=False
        )


        bcm_bus.send(message)

        last_transmitted_output = (
            current_output
        )


        print("\nBCM transmitted:")
        print(
            f"WiperMotorCommand = "
            f"{motor_command}"
        )
        print(
            f"WiperStatus       = "
            f"{wiper_state}"
        )


    # --------------------------------------------------
    # BCM startup
    # --------------------------------------------------

    print(
        "\nBCM simulator started..."
    )

    if ready_event is not None:
        ready_event.set()


    # --------------------------------------------------
    # Main BCM loop
    # --------------------------------------------------

    try:

        while True:

            # --------------------------------------------------
            # Stop request from Test Environment
            # --------------------------------------------------

            if (
                stop_event is not None
                and stop_event.is_set()
            ):
                break


            # --------------------------------------------------
            # Receive CAN frame
            # --------------------------------------------------

            rx_message = bcm_bus.recv(
                timeout=0.01
            )


            if rx_message is not None:

                # ----------------------------------------------
                # 0x100 BCM_INPUTS
                # Driver inputs
                # ----------------------------------------------

                if (
                    rx_message.arbitration_id
                    == bcm_inputs.frame_id
                ):

                    signals = bcm_inputs.decode(
                        rx_message.data
                    )


                    ignition = str(
                        signals["IgnitionStatus"]
                    )

                    wiper_switch = str(
                        signals["WiperSwitch"]
                    )


                    print(
                        "\nBCM received driver inputs:"
                    )

                    print(
                        f"IgnitionStatus = "
                        f"{ignition}"
                    )

                    print(
                        f"WiperSwitch    = "
                        f"{wiper_switch}"
                    )


                # ----------------------------------------------
                # 0x101 WIPER_FEEDBACK
                # Physical position sensor
                # ----------------------------------------------

                elif (
                    rx_message.arbitration_id
                    == wiper_feedback.frame_id
                ):

                    signals = wiper_feedback.decode(
                        rx_message.data
                    )


                    home_position = str(
                        signals["WiperHomePosition"]
                    )


                    print(
                        "\nBCM received wiper feedback:"
                    )

                    print(
                        f"WiperHomePosition = "
                        f"{home_position}"
                    )


            # ==================================================
            # BCM FUNCTIONAL LOGIC
            # ==================================================


            # --------------------------------------------------
            # IGNITION OFF
            # --------------------------------------------------

            if ignition != "ON":

                motor_command = "OFF"

                wiper_state = "PARKED"

                has_left_home = False

                wait_start_time = None


            # --------------------------------------------------
            # IGNITION ON
            # --------------------------------------------------

            else:

                # ==================================================
                # PARKED STATE
                # ==================================================

                if wiper_state == "PARKED":

                    # PARKED normally means motor OFF.
                    motor_command = "OFF"


                    # Start intermittent wiping only if:
                    #
                    # - driver requests INTERMITTENT
                    # - physical blade is at HOME
                    if (
                        wiper_switch == "INTERMITTENT"
                        and home_position == "HOME"
                    ):

                        motor_command = "ON"

                        wiper_state = "WIPING"

                        has_left_home = False

                        wait_start_time = None


                # ==================================================
                # WIPING STATE
                # ==================================================

                elif wiper_state == "WIPING":


                    # ==============================================
                    # REQ-WIP-004
                    #
                    # Driver selects OFF while a wiping
                    # cycle is already active.
                    # ==============================================

                    if wiper_switch == "OFF":


                        # ------------------------------------------
                        # Blade is outside HOME.
                        #
                        # Current wiping cycle must continue.
                        # ------------------------------------------

                        if home_position == "NOT_HOME":

                            motor_command = "ON"

                            has_left_home = True


                        # ------------------------------------------
                        # Blade has left HOME and now
                        # returned HOME.
                        #
                        # Current cycle is complete.
                        # ------------------------------------------

                        elif (
                            home_position == "HOME"
                            and has_left_home
                        ):

                            motor_command = "OFF"

                            wiper_state = "PARKED"

                            has_left_home = False

                            wait_start_time = None


                        # ------------------------------------------
                        # Wiping cycle has just started.
                        #
                        # The motor is already ON, but
                        # NOT_HOME feedback has not yet
                        # arrived.
                        #
                        # Do NOT stop the motor here.
                        # ------------------------------------------

                        else:

                            motor_command = "ON"


                    # ==============================================
                    # Normal INTERMITTENT wiping
                    # ==============================================

                    elif (
                        wiper_switch == "INTERMITTENT"
                    ):


                        # ------------------------------------------
                        # Blade has left HOME.
                        # ------------------------------------------

                        if home_position == "NOT_HOME":

                            has_left_home = True

                            motor_command = "ON"


                        # ------------------------------------------
                        # Blade returned HOME after
                        # completing the wiping cycle.
                        # ------------------------------------------

                        elif (
                            home_position == "HOME"
                            and has_left_home
                        ):

                            motor_command = "OFF"

                            wiper_state = "WAITING"

                            has_left_home = False

                            wait_start_time = (
                                time.monotonic()
                            )


                        # ------------------------------------------
                        # Cycle has just started and
                        # NOT_HOME has not arrived yet.
                        # ------------------------------------------

                        else:

                            motor_command = "ON"


                # ==================================================
                # WAITING STATE
                #
                # REQ-WIP-003
                # ==================================================

                elif wiper_state == "WAITING":

                    motor_command = "OFF"


                    # ----------------------------------------------
                    # Driver cancels intermittent mode
                    # during waiting period.
                    # ----------------------------------------------

                    if (
                        wiper_switch
                        != "INTERMITTENT"
                    ):

                        wiper_state = "PARKED"

                        wait_start_time = None


                    # ----------------------------------------------
                    # Continue intermittent delay
                    # ----------------------------------------------

                    elif (
                        wait_start_time
                        is not None
                    ):

                        elapsed_time = (
                            time.monotonic()
                            - wait_start_time
                        )


                        # ------------------------------------------
                        # REQ-WIP-003
                        #
                        # Start next wiping cycle after
                        # configured intermittent delay.
                        # ------------------------------------------

                        if (
                            elapsed_time
                            >= INTERMITTENT_DELAY
                        ):

                            # New cycle can begin only if
                            # blade is physically at HOME.
                            if (
                                home_position
                                == "HOME"
                            ):

                                motor_command = "ON"

                                wiper_state = "WIPING"

                                has_left_home = False

                                wait_start_time = None


            # --------------------------------------------------
            # Publish BCM output if it changed
            # --------------------------------------------------

            transmit_output()


    # --------------------------------------------------
    # Cleanup
    # --------------------------------------------------

    finally:

        bcm_bus.shutdown()

        print(
            "\nBCM simulator stopped."
        )


# --------------------------------------------------
# Standalone execution
# --------------------------------------------------

if __name__ == "__main__":

    run_bcm()