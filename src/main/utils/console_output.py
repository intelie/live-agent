# -*- coding: utf-8 -*-
import time
import json

__all__ = ['format_and_send']


def format_and_send(event_type, statuses, settings):
    timestamp = get_timestamp()
    event = format_event(timestamp, event_type, statuses, settings)
    print("-----------------------------------------------------")
    print(json.dumps(event))


def format_event(timestamp, event_type, statuses, settings):
    event_data = statuses.copy()
    event_data['__type'] = event_type
    event_data['liverig__index__timestamp'] = timestamp
    return json.dumps(event_data)


def get_timestamp():
    return time.time() * 1000
