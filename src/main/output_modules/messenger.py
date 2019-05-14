# -*- coding: utf-8 -*-
import time
import uuid

__all__ = [
    'format_event',
    'get_timestamp',
]


def format_and_send(message, settings, connection_func=None):
    timestamp = get_timestamp()
    event = format_event(timestamp, message, settings)
    connection_func(event, settings)


def format_event(timestamp, message, settings):
    room_data = settings['room']
    author_data = settings['author']

    return {
        '__type': '__message',
        'uid': str(uuid.uuid4()),
        'createdAt': timestamp,
        'message': message,
        'room': room_data,
        'author': author_data,
    }


def get_timestamp():
    return int(time.time() * 1000)
