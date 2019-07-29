# -*- coding: utf-8 -*-
import logging
import uuid
from enum import Enum

from output_modules import raw
from utils.timestamp import get_timestamp

__all__ = [
    'send_message',
    'maybe_send_message_event',
    'maybe_send_chat_message',
    'format_and_send',
]


MESSAGE_TYPES = Enum(
    'MESSAGE_TYPES',
    'EVENT, CHAT'
)


def send_message(process_name, message, timestamp, process_settings=None, output_info=None, message_type=None):
    if (message_type is None) or (message_type == MESSAGE_TYPES.EVENT):
        maybe_send_message_event(
            process_name,
            message,
            timestamp,
            process_settings=process_settings,
            output_info=output_info
        )

    if (message_type is None) or (message_type == MESSAGE_TYPES.CHAT):
        maybe_send_chat_message(
            process_name,
            message,
            process_settings=process_settings,
            output_info=output_info
        )


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


def maybe_send_chat_message(process_name, message, author_name=None, process_settings=None, output_info=None):
    destination_settings = process_settings['destination']
    room = destination_settings.get('room')
    author = destination_settings.get('author')

    if (room and author):
        connection_func, output_settings = output_info

        if author_name:
            author.update(name=author_name)

        output_settings.update(
            room=room,
            author=author,
        )
        logging.info("{}: Sending message '{}' from {} to {}".format(
            process_name, message, author, room
        ))
        format_and_send(message, output_settings, connection_func=connection_func)
    else:
        logging.warn(
            "{}: Cannot send message, room ({}) and/or author ({}) missing. Message is '{}'",
            process_name, room, author, message
        )


def format_and_send(message, settings, connection_func=None):
    timestamp = get_timestamp()
    event = format_event(timestamp, message, settings)

    logging.debug('Sending message {}'.format(event))
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
