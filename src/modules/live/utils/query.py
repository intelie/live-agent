# -*- coding: utf-8 -*-
import queue
from live_client.utils import logging

from utils import loop

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


def handle_events(processor_func, results_queue, settings, timeout=10):
    event_type = settings.get("event_type")
    monitor_type = settings.get("type")
    process_name = f"{event_type} {monitor_type}"

    monitor_settings = settings.get("monitor", {})
    window_duration = monitor_settings.get("window_duration", 60)
    mnemonics = monitor_settings.get("mnemonics", {})
    index_mnemonic = mnemonics.get("index", "timestamp")

    accumulator = []
    iterations = 0
    while True:
        try:
            event = results_queue.get(timeout=timeout)

            latest_data, missing_curves = validate_event(event, settings)

            if latest_data:
                accumulator, start, end = loop.refresh_accumulator(
                    latest_data, accumulator, index_mnemonic, window_duration
                )

                if accumulator:
                    processor_func(accumulator)

            elif missing_curves:
                logging.info(
                    f"{process_name}: Some curves are missing ({missing_curves}). "
                    f"\nevent was: {event} "
                    f"\nWaiting for more data"
                )

            logging.debug(f"{process_name}: Request {iterations} successful")

        except KeyboardInterrupt:
            logging.info(f"{process_name}: Stopping after {iterations} iterations")
            raise

        except queue.Empty as e:
            logging.exception(e)
            raise

        except Exception as e:
            logging.exception(e)
            handle_events(processor_func, results_queue, settings, timeout=timeout)
            return

        iterations += 1


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
