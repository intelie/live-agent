# -*- coding: utf-8 -*-
import logging
import uuid

from utils.timestamp import get_timestamp

__all__ = [
    'create',
    'format_and_send'
]


def create(process_name, annotation_data, process_settings=None, output_info=None):
    destination_settings = process_settings['destination']
    connection_func, output_settings = output_info

    output_settings.update(
        room=destination_settings['room'],
        author=destination_settings['author'],
        dashboard=destination_settings.get('dashboard', {}),
    )
    logging.info("{}: Creating annotation '{}'".format(
        process_name, annotation_data.get('message', "<EMPTY MESSAGE>")
    ))
    format_and_send(annotation_data, output_settings, connection_func=connection_func)


def format_and_send(annotation_data, settings, connection_func=None):
    timestamp = get_timestamp()
    event = format_event(timestamp, annotation_data, settings)
    connection_func(event, settings)


def format_event(timestamp, annotation_data, settings):
    author_data = settings['author']
    room_data = settings['room']
    dashboard_data = settings['dashboard']

    end = annotation_data.get('end')
    end = end if (end is None) else int(end)

    message_event = annotation_data.copy()
    message_event.update({
        '__type': '__annotations',
        '__src': message_event.get('__src', 'live_agent'),
        'uid': message_event.get('uid', str(uuid.uuid4())),
        'createdAt': int(message_event.get('createdAt', timestamp)),
        'begin': int(message_event.get('begin', timestamp)),
        'end': end,
        'author': author_data.get('name'),
        'room': room_data,
        'dashboardId': dashboard_data.get('id'),
        'dashboard': dashboard_data.get('name'),
        'searchable': True,
    })
    logging.debug('Creating annotation {}'.format(message_event))

    return message_event