# -*- coding: utf-8 -*-

from live_client.utils import logging

__all__ = ["prepare_query", "handle_events"]


def prepare_query(settings):
    event_type = settings.get("event_type")
    mnemonics_settings = settings.get("monitor", {}).get("mnemonics", {})
    query_mnemonics = list(mnemonics_settings.values())

    mnemonics_list = "|".join(query_mnemonics)
    values_pipe_fragments = [
        r"lastv(value:object):if(\mnemonic:{0}) as {0}".format(item) for item in query_mnemonics
    ]
    units_pipe_fragments = [
        r"lastv(uom:object):if(\mnemonic:{0}) as {0}_uom".format(item) for item in query_mnemonics
    ]
    pipe_fragments = values_pipe_fragments + units_pipe_fragments
    mnemonics_pipe = ", ".join(pipe_fragments)

    query = """
        {} mnemonic!:({}) .flags:nocount
        => {} over last second every second
        => @filter({} != null)
    """.format(
        event_type, mnemonics_list, mnemonics_pipe, query_mnemonics[0]
    )
    logging.debug(f'query is "{query}"')

    return query


def handle_events(event, callback, settings, accumulator=None):
    monitor_settings = settings.get("monitor", {})
    window_duration = monitor_settings.get("window_duration", 60)
    mnemonics = monitor_settings.get("mnemonics", {})
    index_mnemonic = mnemonics.get("index", "timestamp")

    if accumulator is None:
        accumulator = []

    try:
        latest_data, missing_curves = validate_event(event, settings)

        if latest_data:
            accumulator, start, end = refresh_accumulator(
                latest_data, accumulator, index_mnemonic, window_duration
            )

            if accumulator:
                callback(accumulator)

        elif missing_curves:
            missing_curve_names = ", ".join(missing_curves)
            logging.info(f"Some curves are missing ({missing_curve_names}) from event {event} ")

    except KeyboardInterrupt:
        logging.info(f"Stopping ")
        raise

    except Exception as e:
        logging.exception(f"Error during query: <{e}>")
        handle_events(event, callback, settings)
        return


def validate_event(event, settings):
    valid_events = []
    mnemonics_settings = settings.get("monitor", {}).get("mnemonics", {})
    expected_curves = set(mnemonics_settings.values())

    event_content = event.get("data", {}).get("content", [])
    if event_content:
        missing_curves = expected_curves
        for item in event_content:
            item_curves = set(item.keys())

            # Which curves are missing from all items in this event?
            missing_curves = missing_curves - item_curves

            # Does this item has all curves?
            is_valid = len(expected_curves - item_curves) == 0
            if is_valid:
                valid_events.append(item)
    else:
        missing_curves = []

    return valid_events, missing_curves


def refresh_accumulator(latest_events, accumulator, index_mnemonic, window_duration):
    # Purge old events and add the new ones
    accumulator.extend(latest_events)

    latest_event = latest_events[-1]
    window_end = latest_event.get(index_mnemonic, 0)
    window_start = window_end - window_duration

    last_index = window_start

    purged_accumulator = []
    for item in accumulator:
        index = item.get(index_mnemonic, 0)
        if (window_start <= index <= window_end) and (index >= last_index):
            purged_accumulator.append(item)
            last_index = index
        elif index < last_index:
            # Reset the accumulator
            purged_accumulator = [item]
            last_index = index

    logging.debug(
        "{} of {} events between {} and {}".format(
            len(purged_accumulator), len(accumulator), window_start, window_end
        )
    )

    return purged_accumulator, window_start, window_end
