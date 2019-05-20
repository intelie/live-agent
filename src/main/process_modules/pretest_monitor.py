# -*- coding: utf-8 -*-
import logging
import requests
from functools import partial
from enum import Enum

import numpy as np
from sklearn.linear_model import LinearRegression

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
    'INACTIVE, DRAWDOWN_START, DRAWDOWN_END, BUILDUP_STABLE, COMPLETE'
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

    # In order to avoid detecting the same event twice we must trim the set of events
    # so we avoid looking into the same events twice
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = filter_events(
        event_list,
        latest_seen_index,
        index_mnemonic,
        pretest_volume_mnemonic
    )

    # Before a drawdown, {pretest_volume_mnemonic} must be zero
    while valid_events and (valid_events[0].get(pretest_volume_mnemonic) > 0):
        valid_events.pop(0)

    # Check if the value was zero and has changed
    if valid_events:
        first_event, last_event = valid_events[0], valid_events[-1]

        first_value = first_event.get(pretest_volume_mnemonic)
        last_value = last_event.get(pretest_volume_mnemonic)
        is_drawdown = last_value > 0

        logging.debug((
            "{}: Start of a drawdown detection: {}; {} -> {}."
        ).format(process_name, is_drawdown, first_value, last_value))
    else:
        is_drawdown = False

    # There was a change.
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
        etim = drawdown_event.get(index_mnemonic, -1)
        pressure = drawdown_event.get(pressure_mnemonic, -1)
        depth = drawdown_event.get(depth_mnemonic, -1)

        message = "Probe {}@{:.0f} ft: Drawdown started at {:.1f} s with pressure {:.2f} psi"  # NOQA
        message_sender(process_name, message.format(probe_name, depth, etim, pressure))

        detected_state = PRETEST_STATES.DRAWDOWN_START
        latest_seen_index = etim
    else:
        detected_state = None

    probe_data.update(latest_seen_index=latest_seen_index)
    return detected_state


def find_buildup(process_name, probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} stabilizes"""
    index_mnemonic = probe_data['index_mnemonic']
    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']

    # In order to avoid detecting the same event twice we must trim the set of events
    # so we avoid looking into the same events twice
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = filter_events(
        event_list,
        latest_seen_index,
        index_mnemonic,
        pretest_volume_mnemonic
    )

    # Check if the value is stable
    if len(valid_events) > 1:
        prev_event, last_event = valid_events[-2], valid_events[-1]

        last_pretest_volume = last_event.get(pretest_volume_mnemonic)
        prev_pretest_volume = prev_event.get(pretest_volume_mnemonic)
        drawdown_stopped = (last_pretest_volume == prev_pretest_volume)

        logging.debug((
            "{}: End of drawdown detection: {}; {} -> {}."
        ).format(process_name, drawdown_stopped, prev_pretest_volume, last_pretest_volume))
    else:
        drawdown_stopped = False

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
        etim = drawdown_event.get(index_mnemonic, -1)
        pressure = drawdown_event.get(pressure_mnemonic, -1)
        depth = drawdown_event.get(depth_mnemonic, -1)

        message = "Probe {}@{:.0f} ft: Drawdown ended at {:.2f} s with pressure {:.2f} psi"  # NOQA
        message_sender(process_name, message.format(probe_name, depth, etim, pressure))

        detected_state = PRETEST_STATES.DRAWDOWN_END
        latest_seen_index = etim
    else:
        detected_state = None

    probe_data.update(latest_seen_index=latest_seen_index)
    return detected_state


def find_stable_buildup(process_name, probe_name, probe_data, event_list, message_sender, targets=None):
    """
    State when the slope of the linear regression of {pressure_mnemonic}
    over {buildup_duration} seconds is <= {target_slope}
    """
    index_mnemonic = probe_data['index_mnemonic']
    pressure_mnemonic = probe_data['pressure_mnemonic']
    depth_mnemonic = probe_data['depth_mnemonic']
    buildup_duration = probe_data['buildup_duration']
    buildup_wait_period = probe_data['buildup_wait_period']
    target_slopes = sorted(targets)
    detected_state = None

    # In order to avoid detecting the same event twice we must trim the set of events
    # so we avoid looking into the same events twice
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = filter_events(
        event_list,
        latest_seen_index,
        index_mnemonic,
        pressure_mnemonic
    )

    logging.debug("{}: Trying to detect a buildup with a slope <= {}, watching {} events".format(
        process_name,
        ', '.join(str(item) for item in target_slopes),
        len(valid_events)
    ))

    data = [
        {
            index_mnemonic: item.get(index_mnemonic),
            pressure_mnemonic: item.get(pressure_mnemonic),
            depth_mnemonic: item.get(depth_mnemonic),
        }
        for item in valid_events
    ]

    target_state = None
    if data:
        start_index = 0
        measured_slopes = []

        while True:
            segment_start = data[start_index][index_mnemonic]
            expected_end = segment_start + buildup_duration

            segment_to_check = [
                item for item in data[start_index:]
                if item[index_mnemonic] <= expected_end
            ]
            segment_end = segment_to_check[-1][index_mnemonic]

            if (segment_end - segment_start) < (buildup_duration * 0.9):
                logging.debug("{}: Not enough data, {} s of data available, {} s are needed".format(
                    process_name, (segment_end - segment_start), buildup_duration
                ))
                break

            ##
            # do detection
            ##
            x = np.array([
                item.get(index_mnemonic) for item in segment_to_check
            ]).reshape((-1, 1))
            y = np.array([
                item.get(pressure_mnemonic) for item in segment_to_check
            ])

            model = LinearRegression().fit(x, y)
            segment_slope = abs(model.coef_[0])
            measured_slopes.append(segment_slope)

            matching_slopes = [
                item for item in target_slopes
                if segment_slope <= item
            ]

            if matching_slopes:
                r_score = model.score(x, y)

                target_slope = matching_slopes[0]
                target_state = targets[target_slope]

                # Use the last event of the segment as reference
                drawdown_event = segment_to_check[-1]
                etim = drawdown_event.get(index_mnemonic, -1)
                pressure = drawdown_event.get(pressure_mnemonic, -1)
                depth = drawdown_event.get(depth_mnemonic, -1)

                message = "Probe {}@{:.0f} ft: Buildup stabilized within {} ({:.3f}, r²: {:.3f}) at {:.2f} s with pressure {:.2f} psi"  # NOQA
                message_sender(
                    process_name,
                    message.format(
                        probe_name,
                        depth,
                        target_slope,
                        segment_slope,
                        r_score,
                        etim,
                        pressure
                    )
                )

                detected_state = target_state
                latest_seen_index = etim
                break
            else:
                start_index += 1

        if detected_state is None:
            logging.debug("{}: Buildup did not stabilize within {}. Measured slopes were: {}".format(
                process_name, max(target_slopes), measured_slopes
            ))

            # If a stable buildup takes too long, give up
            latest_event_index = data[-1].get(index_mnemonic)
            wait_period = latest_event_index - latest_seen_index
            if wait_period > buildup_wait_period:
                message = "Probe {}@{:.0f} ft: Buildup did not stabilize within {} after {} s"  # NOQA
                message_sender(
                    process_name,
                    message.format(probe_name, depth, target_slope, wait_period)
                )

                detected_state = PRETEST_STATES.INACTIVE
                latest_seen_index = latest_event_index

    probe_data.update(latest_seen_index=latest_seen_index)
    return detected_state


def recycle_pump(process_name, probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} returns to zero"""
    index_mnemonic = probe_data['index_mnemonic']
    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']

    # In order to avoid detecting the same event twice we must trim the set of events
    # so we avoid looking into the same events twice
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = filter_events(
        event_list,
        latest_seen_index,
        index_mnemonic,
        pretest_volume_mnemonic
    )

    # Before recycling the pump, {pretest_volume_mnemonic} must be higher than zero
    while valid_events and (valid_events[0].get(pretest_volume_mnemonic) == 0):
        valid_events.pop(0)

    # Check if the value was not zero and has changed
    if valid_events:
        first_event, last_event = valid_events[0], valid_events[-1]

        first_value = first_event.get(pretest_volume_mnemonic)
        last_value = last_event.get(pretest_volume_mnemonic)
        is_reset = last_value == 0

        logging.debug((
            "{}: Pump reset detection: {}; {} -> {}."
        ).format(process_name, is_reset, first_value, last_value))
    else:
        is_reset = False

    # There was a change.
    if is_reset:
        depth_mnemonic = probe_data['depth_mnemonic']
        pressure_mnemonic = probe_data['pressure_mnemonic']

        # Find reset point
        events_during_drawdown = [
            item for item in valid_events
            if item.get(pretest_volume_mnemonic, 0) == 0
        ]

        # Reset finished at the first of these events
        drawdown_event = events_during_drawdown[0]
        etim = drawdown_event.get(index_mnemonic, -1)
        pressure = drawdown_event.get(pressure_mnemonic, -1)
        depth = drawdown_event.get(depth_mnemonic, -1)

        message = "Probe {}@{:.0f} ft: Pump reset at {:.1f} s with pressure {:.2f} psi"  # NOQA
        message_sender(process_name, message.format(probe_name, depth, etim, pressure))

        detected_state = PRETEST_STATES.INACTIVE
        latest_seen_index = etim
    else:
        detected_state = None

    probe_data.update(latest_seen_index=latest_seen_index)
    return detected_state


def find_pretest(process_name, probe_name, probe_data, event_list, functions_map):
    current_state = probe_data.get('process_state', PRETEST_STATES.INACTIVE)
    logging.debug("{}: Pretest monitor for probe {} at state {}".format(
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
        PRETEST_STATES.DRAWDOWN_END: partial(
            find_stable_buildup,
            targets={
                0.01: PRETEST_STATES.COMPLETE,
                0.1: PRETEST_STATES.BUILDUP_STABLE,
            }
        ),
        PRETEST_STATES.BUILDUP_STABLE: partial(
            find_stable_buildup,
            targets={
                0.01: PRETEST_STATES.COMPLETE,
            }
        ),
        PRETEST_STATES.COMPLETE: recycle_pump,
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
    buildup_duration = monitor_settings['buildup_duration']
    buildup_wait_period = monitor_settings['buildup_wait_period']
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

            if accumulator:
                for probe_name, probe_data in probes.items():
                    probe_data.update(
                        index_mnemonic=index_mnemonic,
                        buildup_duration=buildup_duration,
                        buildup_wait_period=buildup_wait_period,
                    )
                    find_pretest(
                        process_name,
                        probe_name,
                        probe_data,
                        accumulator,
                        functions_map,
                    )
            else:
                logging.warning("{}: No events received after index {}".format(
                    process_name, latest_index
                ))

            logging.debug("{}: Request {} successful".format(
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
            raise

        loop.await_next_cycle(interval, process_name)
        iterations += 1

    return
