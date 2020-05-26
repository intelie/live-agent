# -*- coding: utf-8 -*-
from enum import Enum
import csv
from setproctitle import setproctitle

import lasio

from live_client.events import raw, messenger
from live_client.utils import timestamp, logging

from ..utils import loop

__all__ = ["start"]


READ_MODES = Enum("READ_MODES", "SINGLE_PASS, CONTINUOUS")


def update_chat(chat, last_ts, next_ts, index_mnemonic, settings):
    if not chat:
        return

    items_to_send = []
    for item in chat:
        item_index = int(item.get(index_mnemonic, -1))

        if last_ts <= item_index < next_ts:
            items_to_send.append(item)
        elif item_index > next_ts:
            break

    logging.debug("{} messages between {} and {}".format(len(items_to_send), last_ts, next_ts))

    for item in items_to_send:
        message = item.get("MESSAGE", "")
        source = item.get("SOURCE", "")
        if message and source:
            messenger.maybe_send_chat_message(
                message, timestamp.get_timestamp(), settings, author_name=source
            )


def send_message(message, timestamp, settings=None):
    messenger.maybe_send_message_event(message, timestamp, settings)
    messenger.maybe_send_chat_message(message, timestamp, settings)


def delay_output(last_timestamp, next_timestamp):
    if last_timestamp == 0:
        sleep_time = 0
    else:
        sleep_time = max(next_timestamp - last_timestamp, 0)

    loop.await_next_cycle(sleep_time)


def read_next_frame(values_iterator, curves, curves_data, index_mnemonic):
    try:
        index, values = next(values_iterator)
        success = True
    except Exception as e:
        output_frame = {}
        success = False
        logging.debug("Error reading next value, {}<{}>".format(e, type(e)))

    if success:
        output_frame = {index_mnemonic: {"value": index, "uom": "s"}}

        for index, channel in enumerate(curves):
            uom = curves_data.get(channel)
            channel_value = values[index]
            output_frame[channel] = {"value": channel_value, "uom": uom}

    return success, output_frame


def open_files(settings, iterations, mode=READ_MODES.CONTINUOUS):
    path_list = settings["path_list"]
    index_mnemonic = settings["index_mnemonic"]

    if mode == READ_MODES.CONTINUOUS:
        path_index = iterations % len(path_list)
    else:
        path_index = iterations

    try:
        las_path, chat_path = path_list[path_index]
        with open(las_path, "r") as las_file:
            data = lasio.read(las_file)

        if chat_path:
            with open(chat_path, "r") as chat_file:
                chat_data = list(csv.DictReader(chat_file))

            logging.debug("Success opening files {} and {}>".format(las_path, chat_path))
        else:
            chat_data = []
            logging.debug("Success opening file {}>".format(las_path))

        success = True
    except Exception as e:
        data = e
        chat_data = None
        success = False
        logging.error("Error opening file {}, {}<{}>".format(las_path, e, type(e)))

    return success, data, chat_data, index_mnemonic


def generate_events(event_type, las_data, chat_data, index_mnemonic, settings, state_manager):
    logging.info("{}: Event generation started".format(event_type))

    source_name = las_data.version.SOURCE.value
    curves_data = dict((item.mnemonic, item.unit) for item in las_data.curves)
    las_df = las_data.df()
    values_iterator = las_df.iterrows()
    curves = las_df.columns

    success = True
    state = state_manager.load()
    last_timestamp = state.get("last_timestamp", 0)
    if last_timestamp > 0:
        logging.info(f"Skipping to index {last_timestamp}")

    while success:
        success, statuses = read_next_frame(values_iterator, curves, curves_data, index_mnemonic)

        if success:
            next_timestamp = statuses.get(index_mnemonic, {}).get("value", 0)

        if next_timestamp > last_timestamp:
            delay_output(last_timestamp, next_timestamp)

            if last_timestamp == 0:
                message = "Replay from '{}' started at TIME {}".format(source_name, next_timestamp)
                send_message(message, timestamp.get_timestamp(), settings=settings)

            raw.create(event_type, statuses, settings)

            update_chat(chat_data, last_timestamp, next_timestamp, index_mnemonic, settings)
            last_timestamp = next_timestamp
            state_manager.save({"last_timestamp": last_timestamp})


def start(settings, **kwargs):
    """
    Starts the LAS replayer, based on the process settings.

    Replays sensors and chat data.

    :param settings: Parameters for this `las_replayer` instance
    :type settings: dict

    :param state_manager: StateManager injected by `live-agent`
    :type state_manager: live_agent.services.StateManager

    :rtype: NoneType

    The settings for this process have the following format::

      {
        "type": "las_replay",
        "enabled": true,  # Self explanatory
        "index_mnemonic": "TIME",  # Curve used as index for the LAS data
        "path_list": [
          # A list of filename pairs containing the data to be replayed
          [<path for a LAS file>, <path for a CSV file containing the chat logs>],
          ...
        ]
        "output": {
          "event_type": "raw_wellX", The name of the event type which should be sent to Intelie Live
          "author": {
            "id": <user id>  # User id of the author for the messages
            "name": "Linguistics monitor"  # User name of the author for the messages
          },
          "room": {
            "id": <room id>  # Id of the room where the messages should be sent
          },
          "message_event": {
            # Information for generating markers on charts
            "event_type": "raw_wellX",  # Usually the raw event type of the asset being monitored
            "mnemonic": "MSG"  # Mnemonic used for messages normalization, usually named `MSG`
          }
        }
      }

    The LAS file *must* be SPACE delimited.

    The CSV file must contain at least 3 columns:

    - `MESSAGE`: The text of the message
    - `SOURCE`: The name of the message sender
    - A column with the same name a the `index_mnemonic` defined on the process settings,
    used for correlating messages with the events from the LAS file.

    """
    event_type = settings["output"]["event_type"]
    cooldown_time = settings.get("cooldown_time", 300)
    setproctitle('DDA: LAS replayer for "{}"'.format(event_type))

    state_manager = kwargs.get("state_manager")
    state = state_manager.load()
    iterations = state.get("iterations", 0)

    while True:
        try:
            success, las_data, chat_data, index_mnemonic = open_files(
                settings, iterations, mode=READ_MODES.CONTINUOUS
            )

            if success:
                generate_events(
                    event_type, las_data, chat_data, index_mnemonic, settings, state_manager
                )
                logging.info("Iteration {} successful".format(iterations))
            else:
                logging.warn("Could not open files")

            state_manager.save({"last_timestamp": 0, "iterations": iterations}, force=True)
            loop.await_next_cycle(
                cooldown_time,
                message="Sleeping for {:.1f} minutes between runs".format(cooldown_time / 60.0),
                log_func=logging.info,
            )

        except KeyboardInterrupt:
            logging.info("Stopping after {} iterations".format(iterations))
            raise

        except Exception as e:
            logging.error(
                "Error processing events during iteration {}, {}<{}>".format(iterations, e, type(e))
            )

        iterations += 1
        del las_data
        del chat_data

    return
