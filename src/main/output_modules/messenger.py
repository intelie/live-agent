# -*- coding: utf-8 -*-
import logging
import uuid

from utils.timestamp import get_timestamp

__all__ = [
    'send_chat_message',
    'format_and_send',
]


def send_chat_message(process_name, message, process_settings=None, output_info=None):
    destination_settings = process_settings['destination']
    connection_func, output_settings = output_info

    output_settings.update(
        room=destination_settings['room'],
        author=destination_settings['author'],
    )
    logging.info("{}: Sending message '{}'".format(
        process_name, message
    ))
    format_and_send(message, output_settings, connection_func=connection_func)


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
