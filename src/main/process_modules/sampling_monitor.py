# -*- coding: utf-8 -*-
import requests
from functools import partial
from itertools import dropwhile
from enum import Enum
from setproctitle import setproctitle
from eliot import Action

from live_client.events import messenger, annotation
from live_client.utils import timestamp
from utils import loop, monitors
from utils import logging

__all__ = ['start']

"""
Description:

Detect when the pumps are activated, then:
- When only one pump is active: notify pumping rate changes;
- When both pumps are activated in an interval larger than 30 seconds: notify pumping rate changes
    for each pump;
- When both pumps are activated in a 30 seconds interval: notify pumping rate changes, commingled
    flow, focused flow and bottle filling;


Possible alarms:
- The duration of a commingled flow is too short (< 3 mins?)
- Motor speed steady, pumping rates dropped and pressure risen: probable seal loss


Possible states:

ID      DESCRIPTION                           Pump 1 state        Pump 2 state        Sampling state
-----------------------------------------------------------------------------------------------------
0.0     No sampling                          INACTIVE            INACTIVE            INACTIVE

1.0     Pump N activated at ETIM with        PUMPING             INACTIVE            INACTIVE
        flow rate X, pressuse Y

1.1     Pump N rate changed to X at ETIM     PUMPING             INACTIVE            INACTIVE
        with pressure Y

1.2     Pump N deactivated at ETIM with      BUILDUP_EXPECTED    INACTIVE            INACTIVE
        with pressure Y

2.0     Buildup stabilized within 0.1 at     BUILDUP_STABLE      INACTIVE            INACTIVE
        ETIM with pressure X

2.1     Buildup stabilized within 0.01 at    INACTIVE            INACTIVE            INACTIVE
        ETIM with pressure X


3.0     Commingled flow started at ETIM      PUMPING             PUMPING             COMMINGLED_FLOW
        with pressures X and Y (rate X/Y)

3.0a    Alert: Commingled flow too short?    INACTIVE            INACTIVE            INACTIVE

3.1     Outer pump rate changed to X at      PUMPING             PUMPING             COMMINGLED_FLOW
        ETIM with pressure Y
        or Pump N rate changed to X at
        ETIM with pressure Y

3.2     Focused flow started at ETIM         PUMPING             PUMPING             FOCUSED_FLOW
        with pressures X and Y (rate X/Y)
        flow rates (x and y) and
        pump ratio (x/y)

4.0     Bottle filling start at ETIM         PUMPING             INACTIVE            SAMPLING
        with pressure X

4.0a    Alert: Motor speed and flow rate     PUMPING             PUMPING             FOCUSED_FLOW
        diverging. Lost seal?

4.1     Bottle filling end at ETIM with      PUMPING             PUMPING             FOCUSED_FLOW
        with pressure X

3.3     Focused flow finished at ETIM        BUILDUP_EXPECTED    BUILDUP_EXPECTED    INACTIVE
        with pressures X and Y (rate X/Y)


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


def maybe_create_annotation(process_name, current_state, old_state, context, annotation_func=None):
    if 'probe' in context:
        real_func = maybe_create_pump_annotation
        context = context['probe']
    else:
        real_func = maybe_create_sampling_annotation

    return real_func(
        process_name,
        current_state,
        old_state,
        context,
        annotation_func=annotation_func
    )


def maybe_create_pump_annotation(process_name, current_state, old_state, context, annotation_func=None):  # NOQA
    begin = end = None

    probe_name = context['probe_name']
    probe_data = context['probe_data']
    begin = probe_data.get('pump_activation_timestamp', timestamp.get_timestamp())
    end = probe_data.get('pump_deactivation_timestamp')

    if not end:
        ts = begin
        end = begin + 60000  # One minute later than `begin` by default
    else:
        ts = end

    duration = max((end - begin), 0) / 1000

    annotation_templates = {
        PUMP_STATES.PUMPING: {
            'message': "Probe {}: Pump started".format(probe_name),
            '__color': '#E87919',
            'createdAt': begin,
            'begin': begin,
            'end': end,
        },
        PUMP_STATES.BUILDUP_EXPECTED: {
            'message': "Probe {}: Pump activated for {:.0f} seconds".format(probe_name, duration),
            '__color': '#73E819',
            'createdAt': end,
            'begin': begin,
            'end': end,
        },
    }

    annotation_data = annotation_templates.get(current_state)
    if annotation_data:
        annotation_data.update(
            __src='sampling_monitor',
            uid='{}-{}-{:.0f}'.format(
                process_name,
                probe_name,
                ts,
            ),
        )
        annotation_func(probe_name, annotation_data)

    else:
        logging.error('{}, probe {}: Cannot create annotation without data'.format(
            process_name, probe_name
        ))

    return


def maybe_create_sampling_annotation(process_name, current_state, old_state, context, annotation_func=None):  # NOQA
    process_settings = context

    begin = end = None
    if old_state == SAMPLING_STATES.SAMPLING and current_state == SAMPLING_STATES.FOCUSED_FLOW:
        return
    elif current_state == SAMPLING_STATES.COMMINGLED_FLOW:
        begin = process_settings.get('commingled_flow_start_ts', 0)
    elif current_state == SAMPLING_STATES.FOCUSED_FLOW:
        begin = process_settings.get('focused_flow_start_ts', 0)
    else:
        begin = process_settings.get('focused_flow_start_ts', 0)
        end = process_settings.get('focused_flow_end_ts', 0)

    if not end:
        ts = begin
        end = begin + 60000  # One minute later than `begin` by default
    else:
        ts = end

    duration = max((end - begin), 0) / 1000

    annotation_templates = {
        SAMPLING_STATES.COMMINGLED_FLOW: {
            'message': "Commingled flow started",
            '__color': '#FFCC33',
            'createdAt': begin,
            'begin': begin,
            'end': end,
        },
        SAMPLING_STATES.FOCUSED_FLOW: {
            'message': "Focused flow started",
            '__color': '#99FF00',
            'createdAt': begin,
            'begin': begin,
            'end': end,
        },
        SAMPLING_STATES.INACTIVE: {
            'message': "Sampling finished. Operation took {:.0f} seconds".format(duration),
            '__color': '#003399',
            'createdAt': end,
            'begin': begin,
            'end': end,
        },
    }

    annotation_data = annotation_templates.get(current_state)
    if annotation_data:
        annotation_data.update(
            __src='sampling_monitor',
            uid='{}-{}-{:.0f}'.format(
                process_name,
                current_state,
                ts,
            ),
        )
        annotation_func(process_name, annotation_data)

    else:
        logging.error('{}: Cannot create annotation without data'.format(
            process_name
        ))

    return


def find_rate_change(process_name, probe_name, probe_data, event_list, sampling_state, message_sender=None):  # NOQA
    index_mnemonic = probe_data['index_mnemonic']
    flow_rate_mnemonic = probe_data['pumpout_flowrate_mnemonic']
    probe_state = probe_data.get('process_state', PUMP_STATES.INACTIVE)

    pump_activation_timestamp = probe_data.get('pump_activation_timestamp', 0)
    pump_activation_index = probe_data.get('pump_activation_index', 0)
    pump_deactivation_timestamp = probe_data.get('pump_deactivation_timestamp', 0)
    pump_deactivation_index = probe_data.get('pump_deactivation_index', 0)
    rate_change_timestamp = probe_data.get('rate_change_timestamp', 0)
    rate_change_index = probe_data.get('rate_change_index', 0)

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
    latest_flowrate = probe_data.get('latest_flowrate', 0)
    latest_motorspeed = probe_data.get('latest_motorspeed', 0)

    fluctuation_tolerance = 1

    high_cut = latest_flowrate + fluctuation_tolerance
    low_cut = latest_flowrate - fluctuation_tolerance

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
        motor_speed_mnemonic = probe_data['pump_motor_speed_mnemonic']

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
        event_timestamp = reference_event.get('timestamp', timestamp.get_timestamp())

        message = (
            "Probe {}@{:.0f} ft: Flow rate changed at {:.0f}s. "
            "\n   Flow rate: {:.2f} -> {:.2f} cm³/s "
            "\n   Motor speed: {:.2f} -> {:.2f} rpm "
            "\n   Pressure: {:.2f} psi "
        ).format(
            probe_name, depth, etim,
            latest_flowrate, flow_rate,
            latest_motorspeed, motor_speed,
            pressure
        )
        message_sender(
            process_name,
            message,
            timestamp=event_timestamp,
            message_type=messenger.MESSAGE_TYPES.CHAT
        )

        if (flow_rate < 1):
            detected_state = PUMP_STATES.BUILDUP_EXPECTED
        else:
            detected_state = PUMP_STATES.PUMPING

        if probe_state != detected_state:
            if detected_state == PUMP_STATES.PUMPING:
                pump_activation_timestamp = event_timestamp
                pump_activation_index = etim
            else:
                pump_deactivation_timestamp = event_timestamp
                pump_deactivation_index = etim

        latest_flowrate = flow_rate
        latest_motorspeed = motor_speed
        latest_seen_index = etim
        rate_change_timestamp = event_timestamp
        rate_change_index = etim
        logging.debug(message)
    else:
        detected_state = None

    probe_data.update(
        latest_seen_index=latest_seen_index,
        latest_flowrate=latest_flowrate,
        latest_motorspeed=latest_motorspeed,
        pump_activation_timestamp=pump_activation_timestamp,
        pump_activation_index=pump_activation_index,
        pump_deactivation_timestamp=pump_deactivation_timestamp,
        pump_deactivation_index=pump_deactivation_index,
        rate_change_timestamp=rate_change_timestamp,
        rate_change_index=rate_change_index,
    )
    return detected_state


def find_stable_buildup(process_name, probe_name, probe_data, event_list, state, message_sender=None, targets=None, fallback_state=None):  # NOQA
    # Ignore buildups while sampling
    if state in (SAMPLING_STATES.FOCUSED_FLOW, SAMPLING_STATES.SAMPLING):
        detected_state = PUMP_STATES.INACTIVE
    else:
        detected_state = monitors.find_stable_buildup(
            process_name,
            probe_name,
            probe_data,
            event_list,
            message_sender=message_sender,
            targets=targets,
            fallback_state=fallback_state,
        )

    return detected_state


def check_seal_health(process_name, probe_name, probe_data, event_list, sampling_state, message_sender=None):  # NOQA
    index_mnemonic = probe_data['index_mnemonic']
    flow_rate_mnemonic = probe_data['pumpout_flowrate_mnemonic']
    motor_speed_mnemonic = probe_data['pump_motor_speed_mnemonic']
    depth_mnemonic = probe_data['depth_mnemonic']
    buildup_duration = probe_data['buildup_duration']

    has_seal = probe_data.get('has_seal', True)

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get('latest_seen_index', 0)
    valid_events = loop.filter_events(
        event_list,
        latest_seen_index,
        index_mnemonic,
        flow_rate_mnemonic
    )

    # Check whether pump is active but there is no flow or vice-versa
    if valid_events:
        last_event = valid_events[-1]
        last_flowrate = last_event.get(flow_rate_mnemonic)
        last_motor_speed = last_event.get(motor_speed_mnemonic)
        last_index = last_event.get(index_mnemonic)

        is_stopped = (last_motor_speed == last_flowrate == 0)
        is_running = (last_motor_speed > 0) and (last_flowrate > 0)

        if has_seal and (not (is_stopped or is_running)):
            # We found an inconsistency, find out where it started
            if last_motor_speed > 0:
                # When did the flow stop?
                target_mnemonic = flow_rate_mnemonic
                secondary_mnemonic = motor_speed_mnemonic
            else:
                # When did the pump stop?
                target_mnemonic = motor_speed_mnemonic
                secondary_mnemonic = flow_rate_mnemonic

            # Drop all events where {target_mnemonic} > 0
            events_before_stopping = list(
                dropwhile(
                    lambda event: event.get(target_mnemonic) > 0,
                    valid_events
                )
            )

            # There may be an interval where both values are zero. Drop that
            # Drop all events where {target_mnemonic} > 0
            events_before_stopping = list(
                dropwhile(
                    lambda event: (
                        (event.get(target_mnemonic) == 0) and (event.get(secondary_mnemonic) == 0)
                    ),
                    events_before_stopping
                )
            )

            if events_before_stopping:
                # The inconsistency started in the first of these events
                reference_event = events_before_stopping[0]

                # If the inconsistency happened less than {buildup_duration} ago, ignore it
                etim = reference_event.get(index_mnemonic, -1)
                if (last_index - etim) >= buildup_duration:
                    depth = reference_event.get(depth_mnemonic, -1)
                    motor_speed = reference_event.get(motor_speed_mnemonic, -1)
                    flow_rate = reference_event.get(flow_rate_mnemonic, -1)
                    event_timestamp = reference_event.get('timestamp', timestamp.get_timestamp())

                    # Send a message about the seal loss
                    message = (
                        "*Alarm, probable seal loss for probe {}@{:.0f} ft at {:.0f}!*"
                        "\nMotor speed {:.2f} rpm and flow rate {:.2f} cm³/s!"
                    ).format(
                        probe_name, depth, etim, motor_speed, flow_rate
                    )
                    message_sender(process_name, message, timestamp=event_timestamp)

                    has_seal = False
                    latest_seen_index = etim

    probe_data.update(
        has_seal=has_seal,
        latest_seen_index=latest_seen_index,
    )


def find_commingled_flow(process_name, process_settings, event_list, message_sender=None):
    # When both pumps are started we get to commingled flow
    commingled_flow_start_ts = process_settings.get('commingled_flow_start_ts', 0)
    commingled_flow_end_ts = process_settings.get('commingled_flow_end_ts', 0)
    monitor_settings = process_settings['monitor']

    probes = monitor_settings.get('probes', [])
    pumping_probes = [
        item.get('process_state', PUMP_STATES.INACTIVE) == PUMP_STATES.PUMPING
        for item in probes.values()
    ]

    detected_state = None
    if all(pumping_probes):
        pump_activations_timestamps = [
            item.get('pump_activation_timestamp', -1)
            for item in probes.values()
        ]
        pump_activations_indexes = [
            item.get('pump_activation_index', -1)
            for item in probes.values()
        ]

        # If the pumps are activated more than 30 seconds apart from each other, ignore them
        first_activation_timestamp = min(pump_activations_timestamps)
        first_activation_index = min(pump_activations_indexes)
        last_activation_index = max(pump_activations_indexes)
        if (last_activation_index - first_activation_index) < 30:
            commingled_flow_start_ts = first_activation_timestamp
            detected_state = SAMPLING_STATES.COMMINGLED_FLOW

            message = "Commingled flow started at {:.0f}s.".format(first_activation_index)
            message_sender(process_name, message, timestamp=commingled_flow_start_ts)
            logging.info(message)

    process_settings.update(
        latest_seen_index=commingled_flow_start_ts,
        commingled_flow_start_ts=commingled_flow_start_ts,
        commingled_flow_end_ts=commingled_flow_end_ts,
    )
    return detected_state


def find_focused_flow(process_name, process_settings, event_list, message_sender=None):
    # When rates of both pumps are stable for more than {focused_flow_grace_period}
    monitor_settings = process_settings['monitor']
    index_mnemonic = monitor_settings['index_mnemonic']
    focused_flow_grace_period = monitor_settings.get('focused_flow_grace_period', 60)

    commingled_flow_end_ts = process_settings.get('commingled_flow_end_ts', 0)
    focused_flow_start_ts = process_settings.get('focused_flow_start_ts', 0)
    focused_flow_end_ts = process_settings.get('focused_flow_start_ts', 0)
    focused_flow_start_index = process_settings.get('focused_flow_start_index', 0)

    probes = monitor_settings.get('probes', [])
    pumping_probes = [
        item.get('process_state', PUMP_STATES.INACTIVE) == PUMP_STATES.PUMPING
        for item in probes.values()
    ]

    detected_state = None
    if all(pumping_probes):
        rate_changes_timestamps = [
            item.get('rate_change_timestamp', -1)
            for item in probes.values()
        ]
        rate_changes_indexes = [
            item.get('rate_change_index', -1)
            for item in probes.values()
        ]
        flowrates = [item.get('latest_flowrate', 0) for item in probes.values()]
        motor_speeds = [item.get('latest_motorspeed', 0) for item in probes.values()]

        latest_index = event_list[-1].get(index_mnemonic, 0)
        last_activation_index = max(rate_changes_indexes)
        current_flow_duration = latest_index - last_activation_index

        logging.debug("{}: {:.0f}s to {}".format(
            process_name,
            (focused_flow_grace_period - current_flow_duration),
            SAMPLING_STATES.FOCUSED_FLOW
        ))
        if current_flow_duration >= focused_flow_grace_period:
            last_activation_ts = max(rate_changes_timestamps)
            focused_flow_start_ts = last_activation_ts
            focused_flow_start_index = last_activation_index
            commingled_flow_end_ts = last_activation_ts
            detected_state = SAMPLING_STATES.FOCUSED_FLOW

            message = (
                "Focused flow started at {:.0f}s."
                "\n   Flow rates: {:.2f} and {:.2f} cm³/s (ratio: {:.3f})"
                "\n   Motor speeds: {:.2f} and {:.2f} rpm (ratio: {:.3f})"
            ).format(
                last_activation_index,
                flowrates[0], flowrates[1], (flowrates[0] / flowrates[1]),
                motor_speeds[0], motor_speeds[1], (motor_speeds[0] / motor_speeds[1]),
            )
            message_sender(process_name, message, timestamp=focused_flow_start_ts)
            logging.info(message)
    else:
        # COMMINGLED_FLOW stopped
        rate_changes_timestamps = [
            item.get('rate_change_timestamp', -1)
            for item in probes.values()
        ]
        rate_changes_indexes = [
            item.get('rate_change_index', -1)
            for item in probes.values()
        ]

        last_activation_index = max(rate_changes_indexes)
        commingled_flow_end_ts = max(rate_changes_timestamps)
        focused_flow_end_ts = max(rate_changes_timestamps)

        detected_state = SAMPLING_STATES.INACTIVE

    process_settings.update(
        latest_seen_index=focused_flow_start_index,
        commingled_flow_end_ts=commingled_flow_end_ts,
        focused_flow_start_ts=focused_flow_start_ts,
        focused_flow_end_ts=focused_flow_end_ts,
    )
    return detected_state


def find_sampling_start(process_name, process_settings, event_list, message_sender=None):
    # A pump will be stopped in order to collect a sample
    monitor_settings = process_settings['monitor']
    sampling_start_index = process_settings.get('sampling_start_index', 0)
    sampling_start_ts = process_settings.get('sampling_start_ts', 0)
    focused_flow_end_ts = process_settings.get('focused_flow_end_ts', 0)

    detected_state = None
    pumping_probes = []
    idle_probes = []
    probes = monitor_settings.get('probes', [])

    for probe_name, probe_data in probes.items():
        probe_state = probe_data.get('process_state', PUMP_STATES.INACTIVE)
        if probe_state == PUMP_STATES.PUMPING:
            pumping_probes.append(probe_name)
        else:
            idle_probes.append(probe_name)

    logging.debug("{} \nIdle probes: {}\nRunning probes: {}".format(
        process_name,
        idle_probes,
        pumping_probes
    ))

    # The guard probe should be active and the sampling probe should be idle
    if idle_probes and pumping_probes:
        sampling_probe = idle_probes[0]
        sampling_probe_data = probes[sampling_probe]

        # Find out if the pump is running
        index_mnemonic = sampling_probe_data['index_mnemonic']
        motor_speed_mnemonic = sampling_probe_data['pump_motor_speed_mnemonic']
        latest_seen_index = sampling_probe_data.get('latest_seen_index', 0)
        valid_events = loop.filter_events(
            event_list,
            latest_seen_index,
            index_mnemonic,
            motor_speed_mnemonic,
        )

        if valid_events:
            last_motor_speed = valid_events[-1].get(motor_speed_mnemonic)
        else:
            last_motor_speed = -1

        if last_motor_speed == 0:
            rate_change_timestamp = sampling_probe_data.get('rate_change_timestamp', -1)
            rate_change_index = sampling_probe_data.get('rate_change_index', -1)

            sampling_start_ts = rate_change_timestamp
            sampling_start_index = rate_change_index

            message = "Sample collection started at {:.0f}s.".format(
                sampling_start_index,
            )
            message_sender(process_name, message, timestamp=sampling_start_ts)
            logging.info(message)
            detected_state = SAMPLING_STATES.SAMPLING

    elif not idle_probes:
        detected_state = SAMPLING_STATES.FOCUSED_FLOW

    elif not pumping_probes:
        rate_changes_timestamps = [
            item.get('rate_change_timestamp', -1)
            for item in probes.values()
        ]
        focused_flow_end_ts = max(rate_changes_timestamps)
        detected_state = SAMPLING_STATES.INACTIVE

    process_settings.update(
        latest_seen_index=sampling_start_index,
        sampling_start_index=sampling_start_index,
        sampling_start_ts=sampling_start_ts,
        focused_flow_end_ts=focused_flow_end_ts,
    )
    return detected_state


def find_sampling_end(process_name, process_settings, event_list, message_sender=None):
    # When the second pump gets reactivated
    monitor_settings = process_settings['monitor']
    sampling_start_index = process_settings.get('sampling_start_index', 0)
    sampling_start_ts = process_settings.get('sampling_start_ts', 0)
    sampling_end_index = process_settings.get('sampling_end_index', 0)
    sampling_end_ts = process_settings.get('sampling_end_ts', 0)

    probes = monitor_settings.get('probes', [])
    pumping_probes = [
        item.get('process_state', PUMP_STATES.INACTIVE) == PUMP_STATES.PUMPING
        for item in probes.values()
    ]

    detected_state = None
    if all(pumping_probes):
        rate_changes_timestamps = [
            item.get('rate_change_timestamp', -1)
            for item in probes.values()
        ]
        rate_changes_indexes = [
            item.get('rate_change_index', -1)
            for item in probes.values()
        ]

        last_activation_index = max(rate_changes_indexes)
        last_activation_ts = max(rate_changes_timestamps)

        sampling_end_ts = last_activation_ts
        sampling_end_index = last_activation_index
        detected_state = SAMPLING_STATES.FOCUSED_FLOW

        message = (
            "Sample collection finished at {:.0f}s, sampling took {:.0f}s"
        ).format(
            sampling_end_index, (sampling_end_index - sampling_start_index)
        )
        message_sender(process_name, message, timestamp=sampling_end_ts)
        logging.info(message)

    process_settings.update(
        latest_seen_index=sampling_start_index,
        sampling_start_ts=sampling_start_ts,
        sampling_end_index=sampling_end_index,
        sampling_end_ts=sampling_end_ts,
    )
    return detected_state


def run_probe_monitor(process_name, probe_name, probe_data, event_list, sampling_state, functions_map):  # NOQA
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
        sampling_state,
        message_sender=message_func,
    )
    check_seal_health(
        process_name,
        probe_name,
        probe_data,
        event_list,
        sampling_state,
        message_sender=message_func,
    )

    if detected_state and (detected_state != probe_state):
        logging.info("{}: Sampling monitor, probe {}: {} -> {}".format(
            process_name, probe_name, probe_state, detected_state
        ))
        maybe_create_annotation(
            process_name,
            detected_state,
            probe_state,
            context={'probe': {'probe_name': probe_name, 'probe_data': probe_data}},
            annotation_func=annotation_func,
        )
        probe_state = detected_state

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
        process_settings,
        event_list,
        message_sender=message_func,
    )

    if detected_state and (detected_state != sampling_state):
        logging.info("{}: Sampling monitor, {} -> {}".format(
            process_name, sampling_state, detected_state
        ))
        maybe_create_annotation(
            process_name,
            detected_state,
            sampling_state,
            context=process_settings,
            annotation_func=annotation_func,
        )
        sampling_state = detected_state

    process_settings.update(process_state=sampling_state)


def run_monitor(process_name, process_settings, event_list, functions_map):
    process_settings = loop.maybe_reset_latest_index(process_settings, event_list)
    monitor_settings = process_settings['monitor']
    index_mnemonic = monitor_settings['index_mnemonic']
    buildup_duration = monitor_settings['buildup_duration']
    buildup_wait_period = monitor_settings['buildup_wait_period']

    sampling_state = process_settings.get('process_state', SAMPLING_STATES.INACTIVE)

    # Refresh the state for each probe
    probes = monitor_settings.get('probes', [])
    for probe_name, probe_data in probes.items():
        probe_data.update(
            index_mnemonic=index_mnemonic,
            buildup_duration=buildup_duration,
            buildup_wait_period=buildup_wait_period,
        )
        probe_data = loop.maybe_reset_latest_index(probe_data, event_list)
        run_probe_monitor(
            process_name,
            probe_name,
            probe_data,
            event_list,
            sampling_state,
            functions_map,
        )

    # Refresh the state for the sampling process
    probe_data = loop.maybe_reset_latest_index(process_settings, event_list)
    sampling_state = run_sampling_monitor(process_name, process_settings, event_list, functions_map)
    return sampling_state


def start(process_name, process_settings, output_info, _settings, task_id):
    with Action.continue_task(task_id=task_id):
        logging.info("{}: Sampling monitor started".format(process_name))
        setproctitle('DDA: Sampling monitor "{}"'.format(process_name))
        session = requests.Session()

        functions_map = {
            'pump': {
                PUMP_STATES.INACTIVE: find_rate_change,
                PUMP_STATES.PUMPING: find_rate_change,
                PUMP_STATES.BUILDUP_EXPECTED: partial(
                    find_stable_buildup,
                    targets={
                        0.01: PUMP_STATES.INACTIVE,
                        0.1: PUMP_STATES.BUILDUP_STABLE,
                    },
                    fallback_state=PUMP_STATES.INACTIVE,
                ),
                PUMP_STATES.BUILDUP_STABLE: partial(
                    find_stable_buildup,
                    targets={
                        0.01: PUMP_STATES.INACTIVE,
                    },
                    fallback_state=PUMP_STATES.INACTIVE,
                ),
            },
            'sampling': {
                SAMPLING_STATES.INACTIVE: find_commingled_flow,
                SAMPLING_STATES.COMMINGLED_FLOW: find_focused_flow,
                SAMPLING_STATES.FOCUSED_FLOW: find_sampling_start,
                SAMPLING_STATES.SAMPLING: find_sampling_end,
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
