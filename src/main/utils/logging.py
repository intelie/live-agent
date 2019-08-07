# -*- coding: utf-8 -*-
import sys
from functools import partial

from eliot import Message, write_traceback

__all__ = [
    'debug',
    'info',
    'warn',
    'error',
    'exception',
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
