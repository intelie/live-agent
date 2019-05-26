# -*- coding: utf-8 -*-
import logging
import uuid

from output_modules import raw
from utils.timestamp import get_timestamp

__all__ = [
    'send_chat_message',
    'format_and_send',
]


def maybe_send_message_event(process_name, message, timestamp, process_settings=None, output_info=None):
    destination_settings = process_settings['destination']
    message_event = destination_settings.get('message_event', {})
    event_type = message_event.get('event_type')
    messages_mnemonic = message_event.get('mnemonic')

    if (event_type and messages_mnemonic):
        connection_func, output_settings = output_info
        event = {
            'timestamp': timestamp,
            messages_mnemonic: {'value': message}
        }
        logging.info("{}: Sending message event '{}' for '{}'".format(
            process_name, event, event_type
        ))
        raw.format_and_send(event_type, event, output_settings, connection_func=connection_func)


def send_chat_message(process_name, message, process_settings=None, output_info=None):
    destination_settings = process_settings['destination']
    room = destination_settings.get('room')
    author = destination_settings.get('author')

    if (room and author):
        connection_func, output_settings = output_info

        output_settings.update(
            room=room,
            author=author,
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
