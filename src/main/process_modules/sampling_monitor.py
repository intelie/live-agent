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
Description:

Detect when the pumps are activated, then:
- When only one pump is active: notify pumping rate changes;
- When both pumps are activated in an interval larger than 30 seconds: notify pumping rate changes for each pump;
- When both pumps are activated in a 30 seconds interval: notify pumping rate changes, commingled flow, focused flow and bottle filling;


Possible alarms:
- The duration of a commingled flow is too short (< 3 mins?)
- Motor speed steady, pumping rates dropped and pressure risen: probable seal loss

Examples:
- https://shellgamechanger.intelie.com/#/dashboard/54/?mode=view&span=2019-05-28%252009%253A54%253A21%2520to%25202019-05-28%252012%253A50%253A44  # NOQA
- http://localhost:8080/#/dashboard/21/?mode=view&span=2019-05-28%252011%253A36%253A05%2520to%25202019-05-28%252013%253A07%253A28%2520%2520shifted%2520right%2520by%252025%2525  # NOQA


Possible states:

ID      DESCRIPTION                                                         Pump 1 state        Pump 2 state        Sampling state
------------------------------------------------------------------------------------------------------------------------------------
0.0     No sampling                                                         INACTIVE            INACTIVE            INACTIVE

1.0     Pump N activated at ETIM with flow rate X, pressure Y               PUMPING             INACTIVE            INACTIVE
1.1     Pump N rate changed to X at ETIM with pressure Y                    PUMPING             INACTIVE            INACTIVE
1.2     Pump N deactivated at ETIM with pressure Y                          BUILDUP_EXPECTED    INACTIVE            INACTIVE

2.0     Buildup stabilized within 0.1 at ETIM with pressure X               BUILDUP_STABLE      INACTIVE            INACTIVE
2.1     Buildup stabilized within 0.01 at ETIM with pressure X              INACTIVE            INACTIVE            INACTIVE

3.0     Commingled flow started at ETIM with pressures X and Y (rate X/Y)   PUMPING             PUMPING             COMMINGLED_FLOW
3.0a    Alert: Commingled flow too short?                                   INACTIVE            INACTIVE            INACTIVE
3.1     Outer pump rate changed to X at ETIM with pressure Y                PUMPING             PUMPING             COMMINGLED_FLOW
         or Pump N rate changed to X at ETIM with pressure Y
3.2     Focused flow started at ETIM with pressures X and Y (rate X/Y)      PUMPING             PUMPING             FOCUSED_FLOW
         flow rates (x and y) and pump ratio (x/y)

4.0     Bottle filling start at ETIM with pressure X                        PUMPING             INACTIVE            SAMPLING
4.0a    Alert: Motor speed and flow rate diverging. Lost seal?              PUMPING             PUMPING             FOCUSED_FLOW
4.1     Bottle filling end at ETIM with pressure X                          PUMPING             PUMPING             FOCUSED_FLOW

3.3     Focused flow finished at ETIM with pressures X and Y (rate X/Y)     BUILDUP_EXPECTED    BUILDUP_EXPECTED    INACTIVE


State transitions:

         |
         |
         v
    --> 0.0 --> 1.0 -> 1.1 -> 1.2 ---------    --------------------
    |       |    |             ^          |    ^       ^          |
    |       |    |             |          v    |       |          |
    |       |    ---------------    ---> 2.0 --> 2.1 ---          |
    |       |                       |                             |
    |       |         ---> 3.0a -----                             |
    |       |         |                                           |
    |       --> 3.0 --|--------> 3.2 --------------------> 3.3 ---|
    |                 |           ^     |                         |
    |                 ---> 3.1 ---|     |     --> 4.0a -----      |
    |                             |     |     |            |      |
    |                             |     ---> 4.0 --> 4.1 --|      |
    |                             |                        |      |
    |                             --------------------------      |
    |                                                             |
    ---------------------------------------------------------------

"""

PUMP_STATES = Enum(
    'PUMP_STATES',
    'INACTIVE, PUMPING, BUILDUP_EXPECTED, BUILDUP_STABLE'
)
SAMPLING_STATES = Enum(
    'SAMPLING_STATES',
    'INACTIVE, COMMINGLED_FLOW, FOCUSED_FLOW, SAMPLING'
)


def maybe_create_annotation(process_name, probe_name, probe_data, current_state, annotation_func=None):
    begin = probe_data.get('sampling_begin_timestamp')
    end = probe_data.get('sampling_end_timestamp')

    annotation_templates = {
    }

    annotation_data = annotation_templates.get(current_state)
    if annotation_data and begin:
        annotation_data.update(
            __src='sampling_monitor',
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


def find_rate_change(process_name, probe_name, probe_data, event_list, message_sender=None):
    index_mnemonic = probe_data['index_mnemonic']
    flow_rate_mnemonic = probe_data['pumpout_flowrate_mnemonic']

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = loop.filter_events(
        event_list,
        latest_seen_index,
        index_mnemonic,
        flow_rate_mnemonic
    )

    # Check whether, {flow_rate_mnemonic} has changed
    fluctuation_tolerance = 1
    latest_flowrate = probe_data.get('latest_flowrate', 0)
    latest_motorspeed = probe_data.get('latest_motorspeed', 0)
    low_cut = latest_flowrate - fluctuation_tolerance
    high_cut = latest_flowrate + fluctuation_tolerance

    logging.debug("Probe {}: Ignoring flow rates between {:.2f} and {:.2f}".format(
        probe_name, low_cut, high_cut
    ))

    valid_events = list(
        dropwhile(
            lambda event: high_cut >= event.get(flow_rate_mnemonic) > low_cut,
            valid_events
        )
    )

    has_rate_change = len(valid_events) > 0
    if has_rate_change:
        depth_mnemonic = probe_data['depth_mnemonic']
        pressure_mnemonic = probe_data['pressure_mnemonic']
        motor_speed_mnemonic = probe_data['pump_motor_speed']

        # The rate started changing at the first of these events
        # Find out when the rate stabilized, based on the last {flow_rate_mnemonic}
        last_value = valid_events[-1].get(flow_rate_mnemonic)
        new_low_cut = last_value - fluctuation_tolerance
        new_high_cut = last_value + fluctuation_tolerance

        # Drop all events outside of the interval between {new_high_cut} and {new_low_cut}
        events_after_change = list(
            dropwhile(
                lambda event: not (new_high_cut > event.get(flow_rate_mnemonic) >= new_low_cut),
                valid_events
            )
        )

        first_index = events_after_change[0].get(index_mnemonic)
        last_index = events_after_change[-1].get(index_mnemonic)
        new_pressure_is_stable = (last_index - first_index) > 15
    else:
        new_pressure_is_stable = False

    if new_pressure_is_stable:
        # The rate stabilized on the first of these events
        reference_event = events_after_change[0]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)
        motor_speed = reference_event.get(motor_speed_mnemonic, -1)
        flow_rate = reference_event.get(flow_rate_mnemonic, -1)
        pump_activation_timestamp = reference_event.get('timestamp', timestamp.get_timestamp())

        message = (
            "Probe {}@{:.0f} ft: Flow rate changed at {:.1f}s. "
            "\n   Flow rate: {:.2f} -> {:.2f} cm³/s "
            "\n   Motor speed: {:.2f} -> {:.2f} rpm "
            "\n   Pressure: {:.2f} psi "
        ).format(
            probe_name, depth, etim,
            latest_flowrate, flow_rate,
            latest_motorspeed, motor_speed,
            pressure
        )
        message_sender(process_name, message, timestamp=pump_activation_timestamp)

        if (flow_rate < 1):
            detected_state = PUMP_STATES.BUILDUP_EXPECTED

            if (motor_speed > 0):
                # Flow is almost stopping, pumps should also be stopped
                message = "*Alarm, probable seal loss!* \nMotor speed and flow rate diverging for probe {}@{:.2f} ft.".format(
                    probe_name, depth
                )
                message_sender(process_name, message, timestamp=pump_activation_timestamp)
        else:
            detected_state = PUMP_STATES.PUMPING

        latest_flowrate = flow_rate
        latest_motorspeed = motor_speed
        latest_seen_index = etim
        logging.debug(message)
    else:
        detected_state = None
        pump_activation_timestamp = None

    probe_data.update(
        latest_seen_index=latest_seen_index,
        latest_flowrate=latest_flowrate,
        latest_motorspeed=latest_motorspeed,
        pump_activation_timestamp=pump_activation_timestamp,
    )
    return detected_state






def run_probe_monitor(process_name, probe_name, probe_data, event_list, functions_map):
    pump_functions = functions_map['pump']
    message_func = functions_map['send_message']
    annotation_func = functions_map['create_annotation']

    probe_state = probe_data.get('process_state', PUMP_STATES.INACTIVE)
    logging.debug("{}: Sampling monitor, probe {} at state {}".format(
        process_name, probe_name, probe_state
    ))

    state_transition_func = pump_functions[probe_state]
    detected_state = state_transition_func(
        process_name,
        probe_name,
        probe_data,
        event_list,
        message_sender=message_func,
    )

    if detected_state and (detected_state != probe_state):
        logging.info("{}: Sampling monitor, probe {}: {} -> {}".format(
            process_name, probe_name, probe_state, detected_state
        ))
        probe_state = detected_state
        maybe_create_annotation(
            process_name,
            probe_name,
            probe_data,
            probe_state,
            annotation_func=annotation_func,
        )

    probe_data.update(process_state=probe_state)
    return probe_state


def run_sampling_monitor(process_name, process_settings, event_list, functions_map):
    sampling_functions = functions_map['sampling']
    message_func = functions_map['send_message']
    annotation_func = functions_map['create_annotation']

    sampling_state = process_settings.get('process_state', SAMPLING_STATES.INACTIVE)
    logging.debug("{}: Sampling monitor at state {}".format(
        process_name, sampling_state
    ))

    sampling_transition_func = sampling_functions[sampling_state]
    detected_state = sampling_transition_func(
        process_name,
        event_list,
        message_sender=message_func,
    )

    if detected_state and (detected_state != sampling_state):
        logging.info("{}: Sampling monitor, {} -> {}".format(
            process_name, sampling_state, detected_state
        ))
        sampling_state = detected_state
        maybe_create_annotation(
            process_name,
            sampling_state,
            annotation_func=annotation_func,
        )

    process_settings.update(process_state=sampling_state)


def run_monitor(process_name, process_settings, event_list, functions_map):
    process_settings = loop.maybe_reset_latest_index(process_settings, event_list)
    monitor_settings = process_settings['monitor']
    index_mnemonic = monitor_settings['index_mnemonic']
    buildup_duration = monitor_settings['buildup_duration']
    buildup_wait_period = monitor_settings['buildup_wait_period']

    # Refresh the state for each probe
    probes = monitor_settings.get('probes', [])
    for probe_name, probe_data in probes.items():
        probe_data.update(
            index_mnemonic=index_mnemonic,
            buildup_duration=buildup_duration,
            buildup_wait_period=buildup_wait_period,
        )
        run_probe_monitor(process_name, probe_name, probe_data, event_list, functions_map)

    # Refresh the state for the sampling process
    # @@@
    # sampling_state = run_sampling_monitor(process_name, prmat(process_name))


def start(process_name, process_settings, output_info, _settings):
    logging.info("{}: Sampling monitor started".format(process_name))
    session = requests.Session()

    functions_map = {
        'pump': {
            PUMP_STATES.INACTIVE: find_rate_change,
            PUMP_STATES.PUMPING: find_rate_change,
            PUMP_STATES.BUILDUP_EXPECTED: partial(
                monitors.find_stable_buildup,
                targets={
                    0.01: PUMP_STATES.INACTIVE,
                    0.1: PUMP_STATES.BUILDUP_STABLE,
                },
                fallback_state=PUMP_STATES.INACTIVE,
            ),
            PUMP_STATES.BUILDUP_STABLE: partial(
                monitors.find_stable_buildup,
                targets={
                    0.01: PUMP_STATES.INACTIVE,
                },
                fallback_state=PUMP_STATES.INACTIVE,
            ),
        },
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

    iterations = 0
    latest_index = 0
    accumulator = []

    process_settings.update(
        process_state=SAMPLING_STATES.INACTIVE,
        latest_seen_index=latest_index,
        index_mnemonic=index_mnemonic,
    )
    while True:
        try:
            r = session.get(url)
            r.raise_for_status()

            latest_events = r.json()
            accumulator, start, end = loop.refresh_accumulator(
                latest_events, accumulator, index_mnemonic, window_duration
            )

            if accumulator:
                run_monitor(
                    process_name,
                    process_settings,
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
