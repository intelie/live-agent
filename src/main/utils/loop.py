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

    logging.debug("{} events between {} and {} out of {} stored events".format(
        len(purged_accumulator), window_start, window_end, len(accumulator)
    ))

    return purged_accumulator, window_start, window_end


def filter_events(events, window_start, index_mnemonic, value_mnemonic=None):
    events_in_window = [
        item for item in events
        if item.get(index_mnemonic) > window_start
    ]

    if value_mnemonic:
        valid_events = [
            item for item in events_in_window
            if item.get(value_mnemonic) is not None
        ]
    else:
        valid_events = events_in_window

    return valid_events
