# -*- coding: utf-8 -*-
import logging
import requests
from functools import partial
from enum import Enum

from utils import loop

__all__ = ['start']

"""
Sequence of events:

0- No pretest detected
1- Drawdown start at ETIM with pressure X
2- Drawdown end at ETIM with pressure X
3- Buildup stabilized within 0.1 at ETIM with pressure X
4- Buildup stabilized within 0.01 at ETIM with pressure X
5- Pump recycling start at ETIM with pressure X
6- Pump recycling end at ETIM with pressure X

We want to generate notifications for events 1 to 4

https://shellgamechanger.intelie.com/#/dashboard/51/?mode=view&span=2019-05-16%252008%253A47%253A16%2520to%25202019-05-16%252008%253A58%253A46
"""

PRETEST_STATES = Enum(
    'PRETEST_STATES',
    'INACTIVE, DRAWDOWN_START, DRAWDOWN_END, BUILDUP_STABLE, PRETEST_DONE'
)


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


def send_chat_message(process_name, message, process_settings=None, output_info=None):
    destination_settings = process_settings['destination']
    output_func, output_settings = output_info

    output_settings.update(
        room=destination_settings['room'],
        author=destination_settings['author'],
    )
    logging.info("{}: Sending message '{}'".format(
        process_name, message
    ))
    output_func(message, output_settings)


def find_drawdown(process_name, probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} starts to raise"""
    index_mnemonic = probe_data['index_mnemonic']
    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']

    # In order to avoid detecting the same evet twice we must trim the set of events
    # so we avoid looking into the same events twice
    # We also must ignore events without data
    latest_index = probe_data.get('latest_seen_index', 0)
    valid_events = filter_events(
        event_list,
        latest_index,
        index_mnemonic,
        pretest_volume_mnemonic
    )

    # Before a drawdown, {pretest_volume_mnemonic} must be zero
    while valid_events and (valid_events[0].get(pretest_volume_mnemonic) > 0):
        valid_events.pop(0)

    # Check if the value was zero and has changed
    if valid_events:
        first_event, last_event = valid_events[0], valid_events[-1]
        probe_data.update(latest_seen_index=last_event.get(index_mnemonic))

        first_value = first_event.get(pretest_volume_mnemonic)
        last_value = last_event.get(pretest_volume_mnemonic)
        is_drawdown = last_value > 0

        logging.info((
            "{}: Start of a drawdown detection: {}; {} -> {}."
        ).format(process_name, is_drawdown, first_value, last_value))
    else:
        is_drawdown = False

    # There was a change.
    detected_state = None
    if is_drawdown:
        depth_mnemonic = probe_data['depth_mnemonic']
        pressure_mnemonic = probe_data['pressure_mnemonic']

        # Find drawdown start
        events_during_drawdown = [
            item for item in valid_events
            if item.get(pretest_volume_mnemonic, 0) > 0
        ]

        # Drawdown started at the first of these events
        drawdown_event = events_during_drawdown[0]
        etim = drawdown_event.get(index_mnemonic)
        pressure = drawdown_event.get(pressure_mnemonic)
        depth = drawdown_event.get(depth_mnemonic)

        if (etim and pressure and depth):
            message = "Probe {}@{:.0f} ft: Drawdown started at {:.1f} s with pressure {:.2f} psi"  # NOQA
            message_sender(process_name, message.format(probe_name, depth, etim, pressure))
            detected_state = PRETEST_STATES.DRAWDOWN_START

    return detected_state


def find_buildup(process_name, probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} stabilizes"""
    index_mnemonic = probe_data['index_mnemonic']
    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']

    # In order to avoid detecting the same evet twice we must trim the set of events
    # so we avoid looking into the same events twice
    # We also must ignore events without data
    latest_index = probe_data.get('latest_seen_index', 0)
    valid_events = filter_events(
        event_list,
        latest_index,
        index_mnemonic,
        pretest_volume_mnemonic
    )

    # Check if the value is stable
    if len(valid_events) > 1:
        prev_event, last_event = valid_events[-2], valid_events[-1]
        probe_data.update(latest_seen_index=last_event.get(index_mnemonic))

        last_pretest_volume = last_event.get(pretest_volume_mnemonic)
        prev_pretest_volume = prev_event.get(pretest_volume_mnemonic)
        drawdown_stopped = (last_pretest_volume == prev_pretest_volume)

        logging.info((
            "{}: End of drawdown detection: {}; {} -> {}."
        ).format(process_name, drawdown_stopped, prev_pretest_volume, last_pretest_volume))
    else:
        drawdown_stopped = False

    detected_state = None
    if drawdown_stopped:
        depth_mnemonic = probe_data['depth_mnemonic']
        pressure_mnemonic = probe_data['pressure_mnemonic']

        # Find drawdown end
        events_after_drawdown = [
            item for item in valid_events
            if item.get(pretest_volume_mnemonic, 0) == last_pretest_volume
        ]

        # Drawdown finished at the first of these events
        drawdown_event = events_after_drawdown[0]
        etim = drawdown_event.get(index_mnemonic)
        pressure = drawdown_event.get(pressure_mnemonic)
        depth = drawdown_event.get(depth_mnemonic)

        if (etim and pressure and depth):
            message = "Probe {}@{:.0f} ft: Drawdown ended at {:.2f} s with pressure {:.2f} psi"  # NOQA
            message_sender(process_name, message.format(probe_name, depth, etim, pressure))
            detected_state = PRETEST_STATES.DRAWDOWN_END

    return detected_state


def stabilize_buildup(process_name, probe_name, probe_data, event_list, message, slope=1):
    # index_mnemonic = probe_data['index_mnemonic']
    # pressure_mnemonic = probe_data['pressure_mnemonic']
    # valid_events = [
    #     item for item in event_list
    #     if item.get(pressure_mnemonic) is not None
    # ]

    logging.info("{}: Trying to a stable buildup".format(process_name))
    return PRETEST_STATES.INACTIVE


def recycle_pump(process_name, probe_name, probe_data, event_list, message):
    return PRETEST_STATES.INACTIVE


def find_pretest(process_name, probe_name, probe_data, event_list, functions_map):
    current_state = probe_data.get('process_state', PRETEST_STATES.INACTIVE)
    logging.info("{}: Pretest monitor for probe {} at state {}".format(
        process_name, probe_name, current_state
    ))

    message_sender_func = functions_map['send_message']
    state_transition_func = functions_map[current_state]
    detected_state = state_transition_func(
        process_name,
        probe_name,
        probe_data,
        event_list,
        message_sender_func
    )
    if detected_state:
        current_state = detected_state

    probe_data.update(process_state=current_state)
    return current_state


def start(process_name, process_settings, output_info, _settings):
    logging.info("{}: Pretest monitor started".format(process_name))
    session = requests.Session()

    functions_map = {
        PRETEST_STATES.INACTIVE: find_drawdown,
        PRETEST_STATES.DRAWDOWN_START: find_buildup,
        PRETEST_STATES.DRAWDOWN_END: partial(stabilize_buildup, slope=0.1),
        PRETEST_STATES.BUILDUP_STABLE: partial(stabilize_buildup, slope=0.01),
        PRETEST_STATES.PRETEST_DONE: recycle_pump,
        'send_message': partial(
            send_chat_message,
            process_settings=process_settings,
            output_info=output_info
        )
    }

    url = process_settings['request']['url']
    interval = process_settings['request']['interval']

    monitor_settings = process_settings.get('monitor', {})
    index_mnemonic = monitor_settings['index_mnemonic']
    window_duration = monitor_settings['window_duration']
    probes = monitor_settings['probes']

    iterations = 0
    latest_index = 0
    accumulator = []
    while True:
        try:
            r = session.get(url)
            r.raise_for_status()

            latest_events = r.json()
            accumulator, start, end = loop.refresh_accumulator(
                latest_events, accumulator, index_mnemonic, window_duration
            )
            # events_to_check = filter_events(latest_events, latest_index, process_settings)

            if accumulator:
                for probe_name, probe_data in probes.items():
                    probe_data.update(index_mnemonic=index_mnemonic)
                    find_pretest(
                        process_name,
                        probe_name,
                        probe_data,
                        accumulator,
                        functions_map,
                    )

                # latest_event = events_to_check[-1]
                # latest_index = latest_event.get(index_mnemonic, 0)
            else:
                logging.warning("{}: No events received after index {}".format(
                    process_name, latest_index
                ))

            logging.info("{}: Request {} successful".format(
                process_name, iterations
            ))

        except KeyboardInterrupt:
            logging.info(
                "{}: Stopping after {} iterations".format(
                    process_name, iterations
                )
            )
            raise

        except Exception as e:
            logging.error(
                "{}: Error processing events during request {}, {}<{}>".format(
                    process_name, iterations, e, type(e)
                )
            )

        loop.await_next_cycle(interval, process_name)
        iterations += 1

    return
