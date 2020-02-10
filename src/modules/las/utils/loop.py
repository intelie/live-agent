# -*- coding: utf-8 -*-
import time

from live_client.utils import logging

__all__ = ["await_next_cycle"]


def await_next_cycle(sleep_time, message=None, log_func=None):
    if message is None:
        message = "Sleeping for {} seconds".format(sleep_time)

    if log_func is None:
        log_func = logging.debug

    log_func(message)
    time.sleep(sleep_time)
