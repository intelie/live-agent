# -*- coding: utf-8 -*-
from functools import partial
from itertools import dropwhile
from enum import Enum
import queue
from setproctitle import setproctitle
from eliot import Action, start_action

from live_client.utils import timestamp, logging
from utils import loop, monitors

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
read_timeout = 120
request_timeout = (3.05, 5)
max_retries = 5


def maybe_create_annotation(process_name, probe_name, probe_data, current_state, annotation_func=None):  # NOQA
    begin = probe_data.get('pretest_begin_timestamp', timestamp.get_timestamp())
    end = probe_data.get('pretest_end_timestamp')

    if not end:
        ts = begin
        end = begin + 60000  # One minute later than `begin` by default
    else:
        ts = end

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
    if annotation_data:
        annotation_data.update(
            __src='pretest_monitor',
            uid='{}-{}-{:.0f}'.format(
                process_name,
                probe_name,
                ts,
            ),
            createdAt=ts,
            begin=begin,
            end=end,
        )
        annotation_func(probe_name, annotation_data)

    else:
        logging.debug('{}, probe {}: Cannot create annotation without data'.format(
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
        logging.debug("Probe {}: Pretest began at {:.0f}".format(
            probe_name,
            pretest_begin_timestamp
        ))
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


def start(name, settings, helpers=None, task_id=None):
    process_name = f"{name} - pretest"

    if task_id:
        action = Action.continue_task(task_id=task_id)
    else:
        action = start_action(action_type='pretest_monitor')

    with action.context():
        setproctitle('DDA: Pretest monitor "{}"'.format(process_name))
        logging.info("{}: Pretest monitor started".format(process_name))

        functions_map = {
            PRETEST_STATES.INACTIVE: find_drawdown,
            PRETEST_STATES.DRAWDOWN_START: find_buildup,
            PRETEST_STATES.DRAWDOWN_END: partial(
                monitors.find_stable_buildup,
                targets={
                    0.01: PRETEST_STATES.INACTIVE,
                    0.1: PRETEST_STATES.BUILDUP_STABLE,
                },
                fallback_state=PRETEST_STATES.INACTIVE,
            ),
            PRETEST_STATES.BUILDUP_STABLE: partial(
                monitors.find_stable_buildup,
                targets={
                    0.01: PRETEST_STATES.INACTIVE,
                },
                fallback_state=PRETEST_STATES.INACTIVE,
            ),
            'send_message': partial(
                monitors.get_function('send_message', helpers),
                extra_settings=settings,
            ),
            'create_annotation': partial(
                monitors.get_function('create_annotation', helpers),
                extra_settings=settings,
            ),
            'run_query': monitors.get_function(
                'run_query', helpers
            ),
        }

        monitor_settings = settings.get('monitor', {})
        window_duration = monitor_settings['window_duration']
        results_process, results_queue = functions_map.get('run_query')(
            monitors.prepare_query(settings),
            span=f"last {window_duration} seconds",
            realtime=True,
        )
        probes = monitors.init_probes_data(settings)

        def process_events(accumulator):
            for probe_name, probe_data in probes.items():
                run_monitor(
                    process_name,
                    probe_name,
                    probe_data,
                    accumulator,
                    functions_map,
                )

        try:
            monitors.handle_events(process_events, results_queue, settings, timeout=read_timeout)
        except queue.Empty:
            start(name, settings, helpers=helpers, task_id=task_id)

    action.finish()

    return
