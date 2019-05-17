# -*- coding: utf-8 -*-
import logging
import time

__all__ = ['await_next_cycle']


def await_next_cycle(sleep_time, process_name, message=None, log_func=None):
    if message is None:
        message = "Sleeping for {} seconds".format(sleep_time)

    if log_func is None:
        log_func = logging.debug

    log_func(message.format(process_name))
    time.sleep(sleep_time)


def refresh_accumulator(latest_events, accumulator, index_mnemonic, window_duration):
    # Find out the latest timestamp received
    latest_event = latest_events[-1]
    latest_time = latest_event.get(index_mnemonic, 0)
    window_start = latest_time - window_duration

    # Purge old events and add the new ones
    purged_accumulator = [
        item for item in accumulator
        if item.get(index_mnemonic) > window_start
    ]
    purged_accumulator.extend(latest_events)
    return purged_accumulator, window_start, latest_time
