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
    window_end = latest_event.get(index_mnemonic, 0)
    window_start = window_end - window_duration

    seen_indexes = set()

    # Purge old events and add the new ones
    accumulator.extend(latest_events)

    purged_accumulator = []
    for item in accumulator:
        index = item.get(index_mnemonic)
        if (index not in seen_indexes) and (window_start <= index <= window_end):
            purged_accumulator.append(item)
            seen_indexes.add(index)

    return purged_accumulator, window_start, window_end
