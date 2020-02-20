# -*- coding: utf-8 -*-
from setproctitle import setproctitle

from live_client.utils import logging
from live_client.query import on_event
from live_client.events import messenger


__all__ = ["start"]

read_timeout = 120


def build_query(settings):
    event_type = settings.get("event_type")
    monitor_settings = settings.get("monitor", {})
    max_threshold = monitor_settings["max_threshold"]
    window_duration = monitor_settings["window_duration"]
    sampling_frequency = monitor_settings["sampling_frequency"]
    precision = monitor_settings["precision"]

    flowrate_mnemonics = monitor_settings["flowrate_mnemonics"]
    mnemonics_list = "|".join(flowrate_mnemonics)

    query = f"""
        {event_type} mnemonic!:({mnemonics_list})
        => value as current_value,
           value#:round({precision}):dcount() as num_changes,
           value#round({precision}):set() as values_list,
           timestamp:min() as start,
           timestamp:max() as end,
           mnemonic
          by mnemonic
          every {sampling_frequency} seconds over last {window_duration} seconds
        => @filter(num_changes >= {max_threshold})
        => @throttle 1, {window_duration} seconds
    """
    logging.debug(f'query is "{query}"')

    return query


def start(settings, task_id=None, **kwargs):
    logging.info("Flowrate monitor started")
    setproctitle("DDA: Flowrate monitor")

    window_duration = settings["monitor"]["window_duration"]

    fr_query = build_query(settings)
    span = f"last {window_duration} seconds"

    @on_event(fr_query, settings, span=span, timeout=read_timeout)
    def handle_events(event):
        # Generate alerts whether the threshold was reached
        # a new event means another threshold breach
        event_content = event.get("data", {}).get("content", [])

        for item in event_content:
            template = "{} was changed {} times over the last {} seconds, please calm down ({})"
            message = template.format(
                item["mnemonic"],
                int(item["num_changes"]),
                int((int(item["end"]) - int(item["start"])) / 1000),
                item["values_list"],
            )
            messenger.send_message(message, timestamp=item["timestamp"], settings=settings)

        return

    handle_events()
