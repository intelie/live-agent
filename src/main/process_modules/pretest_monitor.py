# -*- coding: utf-8 -*-
import logging
import requests
from functools import partial
from itertools import dropwhile
from enum import Enum

from output_modules import messenger, annotation
from utils import loop, timestamp, monitors

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
    'INACTIVE, DRAWDOWN_START, DRAWDOWN_END, BUILDUP_STABLE'
)


def maybe_create_annotation(process_name, probe_name, probe_data, current_state, annotation_func=None):
    begin = probe_data.get('pretest_begin_timestamp')
    end = probe_data.get('pretest_end_timestamp')
    if end is None:
        duration = 0
    else:
        duration = max((end - begin), 0) / 1000

    annotation_templates = {
        PRETEST_STATES.DRAWDOWN_START: {
            'message': "Probe {}: Pretest in progress".format(probe_name),
            '__color': '#E87919',
        },
        PRETEST_STATES.INACTIVE: {
            'message': "Probe {}: Pretest completed in {:.1f} seconds".format(probe_name, duration),
            '__overwrite': ['uid'],
            '__color': '#73E819',
        }
    }

    annotation_data = annotation_templates.get(current_state)
    if annotation_data and begin:
        annotation_data.update(
            __src='pretest_monitor',
            uid='{}-{}-{:.0f}'.format(
                process_name,
                probe_name,
                begin,
            ),
            createdAt=begin,
            begin=begin,
            end=end,
        )
        annotation_func(probe_name, annotation_data)

    elif not begin:
        logging.error('{}, probe {}: Cannot create annotation without begin timestamp'.format(
            process_name, probe_name
        ))

    return


def find_drawdown(process_name, probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} starts to raise"""
    index_mnemonic = probe_data['index_mnemonic']
    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = loop.filter_events(
        event_list,
        latest_seen_index,
        index_mnemonic,
        pretest_volume_mnemonic
    )

    # Before a drawdown, {pretest_volume_mnemonic} must be zero
    valid_events = list(
        dropwhile(
            lambda event: event.get(pretest_volume_mnemonic) > 0,
            valid_events
        )
    )

    # Check if the value was zero and has changed
    if valid_events:
        events_during_drawdown = list(
            dropwhile(
                lambda event: event.get(pretest_volume_mnemonic) == 0,
                valid_events
            )
        )
        is_drawdown = len(events_during_drawdown) > 0
    else:
        events_during_drawdown = []
        is_drawdown = False

    # There was a change.
    if is_drawdown:
        depth_mnemonic = probe_data['depth_mnemonic']
        pressure_mnemonic = probe_data['pressure_mnemonic']

        # Drawdown started at the first of these events
        reference_event = events_during_drawdown[0]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)
        pretest_begin_timestamp = reference_event.get('timestamp', timestamp.get_timestamp())

        message = "Probe {}@{:.0f} ft: Drawdown started at {:.1f} s with pressure {:.2f} psi"  # NOQA
        message_sender(
            process_name,
            message.format(probe_name, depth, etim, pressure),
            timestamp=pretest_begin_timestamp
        )

        detected_state = PRETEST_STATES.DRAWDOWN_START
        latest_seen_index = etim
        logging.debug("Probe {}: Pretest began at {:.0f}".format(probe_name, pretest_begin_timestamp))
    else:
        detected_state = None
        pretest_begin_timestamp = None

    probe_data.update(
        latest_seen_index=latest_seen_index,
        pretest_begin_timestamp=pretest_begin_timestamp,
    )
    return detected_state


def find_buildup(process_name, probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} stabilizes"""
    index_mnemonic = probe_data['index_mnemonic']
    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = loop.filter_events(
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
        events_after_drawdown = list(
            dropwhile(
                lambda event: event.get(pretest_volume_mnemonic) != last_pretest_volume,
                valid_events
            )
        )

        # Drawdown finished at the first of these events
        reference_event = events_after_drawdown[0]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)

        message = "Probe {}@{:.0f} ft: Drawdown ended at {:.2f} s with pressure {:.2f} psi"  # NOQA
        message_sender(
            process_name,
            message.format(probe_name, depth, etim, pressure),
            timestamp=reference_event.get('timestamp')
        )

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
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = loop.filter_events(
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
            timestamp: item.get('timestamp'),
            index_mnemonic: item.get(index_mnemonic),
            pressure_mnemonic: item.get(pressure_mnemonic),
            depth_mnemonic: item.get(depth_mnemonic),
        }
        for item in valid_events
    ]

    regression_results = monitors.find_slope(
        process_name,
        data,
        index_mnemonic,
        pressure_mnemonic,
        targets=target_slopes,
        target_r=0.5,
        window_size=buildup_duration
    )

    segment_found = regression_results.get('segment')
    pretest_end_timestamp = None
    target_state = None

    if segment_found:
        segment_slope = regression_results.get('segment_slope')
        r_score = regression_results.get('r_score')
        target_slope = regression_results.get('target_slope')
        target_state = targets[target_slope]

        # Use the last event of the segment as reference
        reference_event = segment_found[-1]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)
        pretest_end_timestamp = reference_event.get('timestamp', timestamp.get_timestamp())

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
            ),
            timestamp=pretest_end_timestamp
        )

        detected_state = target_state
        latest_seen_index = etim
        logging.debug("Probe {}: Pretest finished at {:.0f}".format(probe_name, pretest_end_timestamp))

    else:
        measured_slopes = regression_results.get('measured_slopes', [])
        logging.debug("{}: Buildup did not stabilize within {}. Measured slopes were: {}".format(
            process_name, max(target_slopes), measured_slopes
        ))

        # If a stable buildup takes too long, give up
        latest_event_index = data[-1].get(index_mnemonic)
        wait_period = latest_event_index - latest_seen_index
        depth = data[-1].get(depth_mnemonic, -1)
        if wait_period > buildup_wait_period:
            message = "Probe {}@{:.0f} ft: Buildup did not stabilize within {} after {} s"  # NOQA
            message_sender(
                process_name,
                message.format(probe_name, depth, target_slope, wait_period),
                timestamp=reference_event.get('timestamp')
            )

            detected_state = PRETEST_STATES.INACTIVE
            latest_seen_index = latest_event_index

    probe_data.update(
        latest_seen_index=latest_seen_index,
        pretest_end_timestamp=pretest_end_timestamp,
    )
    return detected_state


def find_pump_recycle(process_name, probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} returns to zero"""
    index_mnemonic = probe_data['index_mnemonic']
    pretest_volume_mnemonic = probe_data['pretest_volume_mnemonic']

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = loop.filter_events(
        event_list,
        latest_seen_index,
        index_mnemonic,
        pretest_volume_mnemonic
    )

    # Before recycling the pump, {pretest_volume_mnemonic} must be higher than zero
    # So, we only care for the first zeroed event
    events_with_volume = list(
        dropwhile(
            lambda event: event.get(pretest_volume_mnemonic) > 0,
            valid_events
        )
    )
    is_reset = len(events_with_volume) > 0

    # There was a change.
    if is_reset:
        depth_mnemonic = probe_data['depth_mnemonic']
        pressure_mnemonic = probe_data['pressure_mnemonic']

        # Reset finished at the first of these events
        reference_event = events_with_volume[0]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)

        message = "Probe {}@{:.0f} ft: Pump reset at {:.1f} s with pressure {:.2f} psi"  # NOQA
        message_sender(
            process_name,
            message.format(probe_name, depth, etim, pressure),
            timestamp=reference_event.get('timestamp')
        )

        detected_state = PRETEST_STATES.INACTIVE
        latest_seen_index = etim
    else:
        detected_state = None

    probe_data.update(latest_seen_index=latest_seen_index)
    return detected_state


def run_monitor(process_name, probe_name, probe_data, event_list, functions_map):
    current_state = probe_data.get('process_state', PRETEST_STATES.INACTIVE)
    logging.debug("{}: Pretest monitor for probe {} at state {}".format(
        process_name, probe_name, current_state
    ))

    state_transition_func = functions_map[current_state]
    probe_data = loop.maybe_reset_latest_index(probe_data, event_list)
    detected_state = state_transition_func(
        process_name,
        probe_name,
        probe_data,
        event_list,
        message_sender=functions_map['send_message']
    )

    if (detected_state is None) and (current_state != PRETEST_STATES.INACTIVE):
        # Did the pretest volume get reset?
        detected_state = find_pump_recycle(
            process_name,
            probe_name,
            probe_data,
            event_list,
            message_sender=functions_map['send_message']
        )

    if detected_state and (detected_state != current_state):
        logging.info("{}: Pretest monitor for probe {}, {} -> {}".format(
            process_name, probe_name, current_state, detected_state
        ))
        current_state = detected_state
        maybe_create_annotation(
            process_name,
            probe_name,
            probe_data,
            current_state,
            annotation_func=functions_map['create_annotation']
        )

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
                0.01: PRETEST_STATES.INACTIVE,
                0.1: PRETEST_STATES.BUILDUP_STABLE,
            }
        ),
        PRETEST_STATES.BUILDUP_STABLE: partial(
            find_stable_buildup,
            targets={
                0.01: PRETEST_STATES.INACTIVE,
            }
        ),
        'send_message': partial(
            messenger.send_message,
            process_settings=process_settings,
            output_info=output_info
        ),
        'create_annotation': partial(
            annotation.create,
            process_settings=process_settings,
            output_info=output_info
        ),
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
                    run_monitor(
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
