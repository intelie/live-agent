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

PROCESS_STATES = Enum(
    'PROCESS_STATES',
    'INACTIVE, DRAWDOWN_START, DRAWDOWN_END, BUILDUP_STABLE, PRETEST_DONE'
)


def filter_events(events, window_start, process_settings):
    monitor_settings = process_settings.get('monitor', {})
    index_mnemonic = monitor_settings['index_mnemonic']

    # Purge old events and add the new ones
    purged_events = [
        item for item in events
        if item.get(index_mnemonic) > window_start
    ]
    return purged_events


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


def find_drawdown(process_name, probe_name, probe_data, accumulator, message_sender):
    """State when {pretest_volume_mnemonic} starts to raise"""
    detected_state = None
    is_drawdown = False

    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']
    valid_events = [
        item for item in accumulator
        if item.get(pretest_volume_mnemonic) is not None
    ]

    # Check if the value was zero and has changed
    if valid_events:
        first_value = valid_events[0].get(pretest_volume_mnemonic)
        last_value = valid_events[-1].get(pretest_volume_mnemonic)
        logging.info((
            "{}: Trying to detect the start of a drawdown, "
            "first value: {}, last value: {}."
        ).format(process_name, first_value, last_value))

        while valid_events and (valid_events[0].get(pretest_volume_mnemonic) > 0):
            valid_events.pop(0)

        is_drawdown = valid_events and (last_value > 0)

    if is_drawdown:
        index_mnemonic = probe_data['index_mnemonic']
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
            detected_state = PROCESS_STATES.DRAWDOWN_START

    return detected_state


def find_buildup(process_name, probe_name, probe_data, accumulator, message_sender):
    """State when {pretest_volume_mnemonic} stabilizes"""
    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']
    valid_events = [
        item for item in accumulator
        if item.get(pretest_volume_mnemonic) is not None
    ]

    # Check if the value is stable
    last_pretest_volume = valid_events[-1].get(pretest_volume_mnemonic)
    prev_pretest_volume = valid_events[-2].get(pretest_volume_mnemonic)

    logging.info((
        "{}: Trying to detect the end of a drawdown, "
        "first value: {}, last value: {}."
    ).format(process_name, prev_pretest_volume, last_pretest_volume))
    drawdown_stopped = (last_pretest_volume == prev_pretest_volume)

    if drawdown_stopped:
        index_mnemonic = probe_data['index_mnemonic']
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
            detected_state = PROCESS_STATES.DRAWDOWN_END

    else:
        detected_state = None

    return detected_state


def stabilize_buildup(process_name, probe_name, probe_data, accumulator, message, slope=1):
    return PROCESS_STATES.INACTIVE


def recycle_pump(process_name, probe_name, probe_data, accumulator, message):
    return PROCESS_STATES.INACTIVE


def find_pretest(process_name, probe_name, probe_data, accumulator, message_sender):
    logging.info("{}: Pretest monitor for probe {}".format(process_name, probe_name))
    STATES_MAP = {
        PROCESS_STATES.INACTIVE: find_drawdown,
        PROCESS_STATES.DRAWDOWN_START: find_buildup,
        PROCESS_STATES.DRAWDOWN_END: partial(stabilize_buildup, slope=0.1),
        PROCESS_STATES.BUILDUP_STABLE: partial(stabilize_buildup, slope=0.01),
        PROCESS_STATES.PRETEST_DONE: recycle_pump,
    }

    current_state = probe_data.get('process_state', PROCESS_STATES.INACTIVE)
    state_transition_func = STATES_MAP[current_state]

    detected_state = state_transition_func(
        process_name,
        probe_name,
        probe_data,
        accumulator,
        message_sender
    )
    if detected_state:
        next_state = detected_state
    else:
        next_state = current_state

    return next_state


def start(process_name, process_settings, output_info, _settings):
    logging.info("{}: Pretest monitor started".format(process_name))
    session = requests.Session()

    message_sender = partial(
        send_chat_message,
        process_settings=process_settings,
        output_info=output_info
    )

    url = process_settings['request']['url']
    interval = process_settings['request']['interval']
    monitor_settings = process_settings.get('monitor', {})
    index_mnemonic = monitor_settings['index_mnemonic']
    probes = monitor_settings['probes']

    iterations = 0
    latest_index = 0
    while True:
        try:
            r = session.get(url)
            r.raise_for_status()

            latest_events = r.json()
            events_to_check = filter_events(latest_events, latest_index, process_settings)

            for probe_name, probe_data in probes.items():
                probe_data.update(index_mnemonic=index_mnemonic)
                next_state = find_pretest(
                    process_name,
                    probe_name,
                    probe_data,
                    events_to_check,
                    message_sender
                )
                probe_data.update(process_state=next_state)

            logging.info("{}: Request {} successful".format(
                process_name, iterations
            ))

        except Exception as e:
            logging.error(
                "{}: Error processing events during request {}, {}<{}>".format(
                    process_name, iterations, e, type(e)
                )
            )

        loop.await_next_cycle(interval, process_name)
        iterations += 1
        latest_value = events_to_check[-1]
        latest_index = latest_value.get(index_mnemonic, 0)

    return
