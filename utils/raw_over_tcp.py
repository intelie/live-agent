# -*- coding: utf-8 -*-
import time
import json

from .collector_client import send_event

__all__ = [
    'send_event',
    'format_event',
    'get_timestamp',
]


def format_and_send(statuses, settings):
    timestamp = get_timestamp()
    event = format_event(timestamp, statuses, settings)
    send_event(event, settings)


def format_event(timestamp, statuses, settings):
    output_settings = settings['output']
    event_type = output_settings['event_type']

    event_data = statuses.copy()
    event_data['__type'] = event_type
    event_data['liverig__index__timestamp'] = timestamp
    return json.dumps(event_data)


def get_timestamp():
    return time.time() * 1000
