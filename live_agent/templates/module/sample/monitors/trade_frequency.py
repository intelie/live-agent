# -*- coding: utf-8 -*-
from setproctitle import setproctitle

from live_client.utils import logging
from live_client.query import on_event
from live_client.events import messenger


__all__ = ["start"]

read_timeout = 120


def start(settings, **kwargs):
    logging.info("Trade frequency monitor started")
    setproctitle("DDA: Trade frequency monitor")

    monitor_settings = settings.get("monitor", {})
    window_duration = monitor_settings.get("window_duration", 60)
    sampling_frequency = monitor_settings.get("sampling_frequency", 30)
    max_threshold = monitor_settings.get("max_threshold", 100)

    fr_query = f"""krakenfx
        => count() by pair every {sampling_frequency} seconds over last {window_duration} seconds
        => @filter(count > {max_threshold})
    """
    span = f"last {window_duration} seconds"

    @on_event(fr_query, settings, span=span, timeout=read_timeout)
    def handle_events(event):
        # Generate alerts whether the threshold was reached
        # a new event means another threshold breach
        event_content = event.get("data", {}).get("content", [])

        for item in event_content:
            template = "{} traded {} times over the last {} seconds"
            message = template.format(item["pair"], int(item["count"]), window_duration)
            messenger.send_message(message, timestamp=item["timestamp"], settings=settings)

        return

    handle_events()
