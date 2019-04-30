# -*- coding: utf-8 -*-
import time
import json

from .collector_client import send_event

__all__ = [
    'send_event',
    'format_event',
    'get_timestamp',
]


def format_and_send(event_type, statuses, settings):
    timestamp = get_timestamp()
    event = format_event(timestamp, event_type, statuses, settings)
    send_event(event, settings)


def format_event(timestamp, event_type, statuses, settings):
    event_data = statuses.copy()
    event_data['__type'] = event_type
    event_data['liverig__index__timestamp'] = timestamp
    return json.dumps(event_data)


def get_timestamp():
    return time.time() * 1000
