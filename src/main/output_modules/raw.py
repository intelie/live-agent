# -*- coding: utf-8 -*-
import time

__all__ = [
    'format_event',
    'get_timestamp',
]


def format_and_send(event_type, statuses, settings, connection_func=None):
    timestamp = get_timestamp()
    event = format_event(timestamp, event_type, statuses, settings)
    connection_func(event, settings)


def format_event(timestamp, event_type, statuses, settings):
    event_data = statuses.copy()
    event_data['__type'] = event_type
    event_data['liverig__index__timestamp'] = timestamp
    return event_data


def get_timestamp():
    return time.time() * 1000
