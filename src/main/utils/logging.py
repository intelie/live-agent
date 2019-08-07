# -*- coding: utf-8 -*-
import sys
from functools import partial

from eliot import Message, write_traceback, add_destinations

from live_client.connection.rest_input import send_event

__all__ = [
    'debug',
    'info',
    'warn',
    'error',
    'exception',
    'log_to_live',
]


def log_message(message, severity=None):
    return Message.log(message_type=severity, message=message)


def exception(message):
    log_message(message, severity='exception')
    write_traceback(exc_info=sys.exc_info())


debug = partial(log_message, severity='debug')
info = partial(log_message, severity='info')
warn = partial(log_message, severity='warn')
error = partial(log_message, severity='error')


def log_to_live(message, event_type=None, username=None, password=None, url=None):
    log_output_settings = {
        'url': url,
        'username': username,
        'password': password
    }

    message.update(__type=event_type)
    send_event(message, log_output_settings)


def setup_live_logging(settings):
    log_settings = settings.get('output', {}).get('rest-log', {})

    event_type = log_settings.get('event_type', 'dda_log')
    url = log_settings.get('url')
    username = log_settings.get('username')
    password = log_settings.get('password')

    if event_type and url and username and password:
        add_destinations(
            partial(
                log_to_live,
                event_type=event_type,
                username=username,
                password=password,
                url=url
            )
        )
