from pathlib import Path
import csv
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


# --------------------------------------------------
# Load DBC
# --------------------------------------------------

db = cantools.database.load_file(DBC_FILE)


# --------------------------------------------------
# CAN Trace Logger
# --------------------------------------------------

def run_can_logger(
    trace_file,
    start_time,
    ready_event=None,
    stop_event=None
):

    # --------------------------------------------------
    # Create passive CAN listener
    # --------------------------------------------------

    logger_bus = can.Bus(
        interface="virtual",
        channel="wiper_network"
    )


    # --------------------------------------------------
    # Prepare trace file
    # --------------------------------------------------

    trace_file = Path(trace_file)

    trace_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    # --------------------------------------------------
    # Helper:
    # Convert decoded DBC signals into readable text
    #
    # Example:
    #
    # IgnitionStatus=ON;
    # WiperSwitch=INTERMITTENT
    # --------------------------------------------------

    def format_signals(decoded_signals):

        formatted_signals = []

        for signal_name, signal_value in decoded_signals.items():

            formatted_signals.append(
                f"{signal_name}={signal_value}"
            )

        return "; ".join(
            formatted_signals
        )


    # --------------------------------------------------
    # Helper:
    # Process one received CAN message
    # --------------------------------------------------

    def process_message(
        message,
        writer,
        trace_handle
    ):

        # ----------------------------------------------
        # Relative timestamp
        #
        # All CAN frames are referenced to the
        # beginning of the test execution.
        # ----------------------------------------------

        relative_time = (
            time.monotonic()
            - start_time
        )


        # ----------------------------------------------
        # Raw CAN payload
        #
        # Example:
        # 03 00 00 00 00 00 00 00
        # ----------------------------------------------

        data_hex = " ".join(
            f"{byte:02X}"
            for byte in message.data
        )


        # ----------------------------------------------
        # Default values
        #
        # These remain if the CAN ID is unknown
        # or cannot be decoded using the DBC.
        # ----------------------------------------------

        message_name = "UNKNOWN"

        sender = ""

        decoded_text = ""


        # ----------------------------------------------
        # DBC decoding
        # ----------------------------------------------

        try:

            dbc_message = (
                db.get_message_by_frame_id(
                    message.arbitration_id
                )
            )


            message_name = (
                dbc_message.name
            )


            if dbc_message.senders:

                sender = ", ".join(
                    dbc_message.senders
                )


            decoded_signals = (
                dbc_message.decode(
                    message.data
                )
            )


            decoded_text = (
                format_signals(
                    decoded_signals
                )
            )


        except (
            KeyError,
            cantools.database.errors.DecodeError
        ):

            # --------------------------------------------------
            # Unknown or undecodable CAN frame.
            #
            # Raw CAN information is still stored in the CSV.
            # --------------------------------------------------

            pass


        # ----------------------------------------------
        # Write one CAN frame into the CSV trace
        # ----------------------------------------------

        writer.writerow({
            "Time_s": f"{relative_time:.6f}",
            "CAN_ID": (
                f"0x{message.arbitration_id:03X}"
            ),
            "Message": message_name,
            "Sender": sender,
            "DLC": message.dlc,
            "Data": data_hex,
            "Decoded_Signals": decoded_text
        })


        # ----------------------------------------------
        # Immediately flush data to disk
        #
        # This reduces the risk of losing trace
        # information if the test stops unexpectedly.
        # ----------------------------------------------

        trace_handle.flush()


    # --------------------------------------------------
    # Open CSV trace file
    #
    # mode="w" creates a fresh trace every time
    # the test is executed.
    # --------------------------------------------------

    with open(
        trace_file,
        mode="w",
        newline="",
        encoding="utf-8"
    ) as trace_handle:


        # --------------------------------------------------
        # CSV columns
        # --------------------------------------------------

        fieldnames = [
            "Time_s",
            "CAN_ID",
            "Message",
            "Sender",
            "DLC",
            "Data",
            "Decoded_Signals"
        ]


        writer = csv.DictWriter(
            trace_handle,
            fieldnames=fieldnames
        )


        writer.writeheader()

        trace_handle.flush()


        # --------------------------------------------------
        # Logger successfully initialized
        # --------------------------------------------------

        print(
            "\nCAN Trace Logger started."
        )

        print(
            f"Trace file: {trace_file}"
        )


        if ready_event is not None:

            ready_event.set()


        # --------------------------------------------------
        # Main logger loop
        # --------------------------------------------------

        try:

            while True:

                # ------------------------------------------
                # Receive CAN traffic
                # ------------------------------------------

                message = logger_bus.recv(
                    timeout=0.05
                )


                # ------------------------------------------
                # A CAN frame was received
                # ------------------------------------------

                if message is not None:

                    process_message(
                        message,
                        writer,
                        trace_handle
                    )


                # ------------------------------------------
                # Logger shutdown requested
                #
                # The test should only set this event
                # AFTER the BCM and Wiper Motor have
                # already stopped.
                # ------------------------------------------

                if (
                    stop_event is not None
                    and stop_event.is_set()
                ):

                    # --------------------------------------
                    # Drain remaining CAN messages
                    #
                    # Since the producing nodes should
                    # already be stopped, everything
                    # remaining in the receive queue can
                    # safely be written before shutdown.
                    # --------------------------------------

                    while True:

                        remaining_message = (
                            logger_bus.recv(
                                timeout=0.0
                            )
                        )


                        if remaining_message is None:

                            break


                        process_message(
                            remaining_message,
                            writer,
                            trace_handle
                        )


                    break


        # --------------------------------------------------
        # Logger cleanup
        # --------------------------------------------------

        finally:

            logger_bus.shutdown()

            print(
                "\nCAN Trace Logger stopped."
            )

            print(
                f"Trace saved to: {trace_file}"
            )