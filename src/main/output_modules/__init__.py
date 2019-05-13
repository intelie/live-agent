# -*- coding: utf-8
from functools import partial
from . import (
    raw,
    messenger,
    console_output
)

from live_client import (
    collector,
    rest_input
)

__all__ = ['OUTPUT_HANDLERS']

OUTPUT_HANDLERS = {
    'raw_over_tcp': partial(
        raw.format_and_send,
        connection_func=collector.send_event
    ),
    'raw_over_rest': partial(
        raw.format_and_send,
        connection_func=rest_input.send_event
    ),
    'chat_over_tcp': partial(
        messenger.format_and_send,
        connection_func=rest_input.send_event
    ),
    'chat_over_rest': partial(
        messenger.format_and_send,
        connection_func=rest_input.send_event
    ),
    'console': console_output.format_and_send,
}
