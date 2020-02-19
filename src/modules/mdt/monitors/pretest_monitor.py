# -*- coding: utf-8 -*-
from functools import partial
from itertools import dropwhile
from enum import Enum
from hashlib import md5
from setproctitle import setproctitle
from eliot import Action, start_action

from live_client.utils import timestamp, logging
from live_client.events import messenger, annotation, raw
from live_client.query import on_event
from live.utils.query import prepare_query, handle_events as process_event
from .utils import loop, probes, buildup

__all__ = ["start"]

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

State transitions:

      |
      v
    INACTIVE --> DRAWDOWN_START --> DRAWDOWN_END ---> BUILDUP_STABLE--
      ^                                           |                  |
      |                                           v                  v
      ----------------------------------------------------------------
           ^                                 |
           |                                 v
           -- RECYCLE_END <-- RECYCLE_START --

Also, we want to generate events to populate a pretests summary report
"""

PRETEST_STATES = Enum("PRETEST_STATES", "INACTIVE, DRAWDOWN_START, DRAWDOWN_END, BUILDUP_STABLE")
DRAWDOWN_END_STATES = (PRETEST_STATES.DRAWDOWN_END, PRETEST_STATES.BUILDUP_STABLE)
PRETEST_END_STATES = (PRETEST_STATES.BUILDUP_STABLE, PRETEST_STATES.INACTIVE)
PRETEST_REPORT_EVENT_TYPE = "pretest_report"

read_timeout = 120
request_timeout = (3.05, 5)
max_retries = 5


def maybe_create_annotation(probe_name, probe_data, current_state, annotation_func=None):
    begin = probe_data.get("pretest_begin_timestamp", timestamp.get_timestamp())
    end = probe_data.get("pretest_end_timestamp")

    if not end:
        ts = begin
        end = begin + 60000  # One minute later than `begin` by default
    else:
        ts = end

    duration = max((end - begin), 0) / 1000

    annotation_templates = {
        PRETEST_STATES.DRAWDOWN_START: {
            "message": f"Probe {probe_name}: Pretest in progress",
            "__color": "#E87919",
        },
        PRETEST_STATES.INACTIVE: {
            "message": "Probe {}: Pretest completed in {:.1f} seconds".format(probe_name, duration),
            "__overwrite": ["uid"],
            "__color": "#73E819",
        },
    }

    annotation_data = annotation_templates.get(current_state)
    if annotation_data:
        annotation_data.update(
            __src="pretest_monitor",
            uid="{}-{:.0f}".format(probe_name, ts),
            createdAt=ts,
            begin=begin,
            end=end,
        )
        annotation_func(annotation_data)

    else:
        logging.info(f"Probe {probe_name}: Cannot create annotation without data")

    return


def find_reference_event(reference_index, event_list, probe_data):
    index_mnemonic = probe_data["index_mnemonic"]
    events = [item for item in event_list if item.get(index_mnemonic) == reference_index]
    if events:
        event = events.pop()
    else:
        event = None

    return event


def get_average(event_list, mnemonic, start, end):
    slice_events = event_list[start:end]
    values = [item.get(mnemonic) for item in slice_events if item.get(mnemonic) is not None]
    average_value = sum(values) / len(values)
    return average_value


def get_value(event, mnemonic):
    return event.get(mnemonic)


def get_uom(event, mnemonic):
    return event.get(f"{mnemonic}_uom")


def get_datum(event, mnemonic):
    return dict(value=get_value(event, mnemonic), uom=get_uom(event, mnemonic))


def maybe_update_pretest_report(probe_name, probe_data, state, event_list, event_sender):
    prev_state = probe_data.get("process_state", PRETEST_STATES.INACTIVE)
    pretest_report = probe_data.get("pretest_report", {})

    reference_index = probe_data.get("latest_seen_index")
    if reference_index and (state != prev_state):

        logging.debug(f"maybe_update_pretest_report: state: {state}, prev_state: {prev_state}")

        reference_event = find_reference_event(reference_index, event_list, probe_data)
        reference_event_index = event_list.index(reference_event)

        if prev_state is PRETEST_STATES.INACTIVE and state is PRETEST_STATES.DRAWDOWN_START:
            """
            pretest has started, collect:

            - event_type
            - probe name
            - drawdown start etim
            - drawdown start timestamp
            - pretest number
            - probe depth
            - hydrostatic pressure before
            - initial volume
            """
            event_type = probe_data["event_type"]
            pretest_number_mnemonic = probe_data["pretest_number_mnemonic"]
            depth_mnemonic = probe_data["depth_mnemonic"]
            pressure_mnemonic = probe_data["pressure_mnemonic"]
            pretest_volume_mnemonic = probe_data["pretest_volume_mnemonic"]

            pretest_begin_timestamp = probe_data.get("pretest_begin_timestamp")
            pretest_number = get_datum(reference_event, pretest_number_mnemonic)
            probe_depth = get_datum(reference_event, depth_mnemonic)

            previous_index = reference_event_index - 1
            average_pressure_before = {
                "value": get_average(
                    event_list, pressure_mnemonic, previous_index - 10, previous_index
                ),
                "uom": get_uom(reference_event, pressure_mnemonic),
            }

            previous_event = event_list[previous_index]
            initial_volume = get_datum(previous_event, pretest_volume_mnemonic)

            pretest_report.update(
                event_type=event_type,
                probe_name=probe_name,
                pretest_begin_etim=reference_index,
                pretest_begin_timestamp=pretest_begin_timestamp,
                pretest_number=pretest_number,
                probe_depth=probe_depth,
                average_pressure_before=average_pressure_before,
                initial_volume=initial_volume,
            )

        elif prev_state is PRETEST_STATES.DRAWDOWN_START and state is PRETEST_STATES.DRAWDOWN_END:
            """
            drawdown finished, collect:

            - drawdown end etim
            - drawdown end timestamp
            - formation pressure
            - temperature
            - pretest volume
            - flow rate
            """

            pretest_begin_timestamp = probe_data.get("pretest_begin_timestamp")
            drawdown_end_timestamp = probe_data.get("drawdown_end_timestamp")
            if pretest_begin_timestamp and drawdown_end_timestamp:
                drawdown_duration = (drawdown_end_timestamp - pretest_begin_timestamp) / 1000
            else:
                drawdown_duration = None

            pressure_mnemonic = probe_data["pressure_mnemonic"]
            pretest_volume_mnemonic = probe_data["pretest_volume_mnemonic"]
            temperature_mnemonic = probe_data["temperature_mnemonic"]

            formation_pressure = get_datum(reference_event, pressure_mnemonic)
            temperature = get_datum(reference_event, temperature_mnemonic)
            pretest_volume = get_datum(reference_event, pretest_volume_mnemonic)

            if drawdown_duration:
                flow_rate = {
                    "value": (pretest_volume.get("value", 0) / drawdown_duration),
                    "uom": "{}/s".format(pretest_volume.get("uom"), "vol"),
                }
            else:
                flow_rate = None

            pretest_report.update(
                drawdown_end_etim=reference_index,
                drawdown_end_timestamp=drawdown_end_timestamp,
                drawdown_duration=drawdown_duration,
                formation_pressure=formation_pressure,
                temperature=temperature,
                pretest_volume=pretest_volume,
                flow_rate=flow_rate,
            )

        elif prev_state in DRAWDOWN_END_STATES and state in PRETEST_STATES:
            """
            found an stable buildup or the end of the pretest, collect:

            - pretest end etim
            - pretest end timestamp
            - buildup slope
            hydrostatic pressure after (before stabilization)
            """

            pressure_mnemonic = probe_data["pressure_mnemonic"]
            average_pressure_after = None

            buildup_slope = probe_data.get("buildup_slope")
            stable_buildup = buildup_slope is not None
            if stable_buildup:
                pretest_end_etim = reference_index
                pretest_end_timestamp = probe_data.get("pretest_end_timestamp")

            elif pretest_report.get("buildup_slope") is not None:
                # We might already have seen a stable buildup
                pretest_end_etim = pretest_report.get("pretest_end_etim")
                reference_event = find_reference_event(pretest_end_etim, event_list, probe_data)
                reference_event_index = event_list.index(reference_event)

                pretest_end_timestamp = pretest_report.get("pretest_end_timestamp")
                buildup_slope = pretest_report.get("buildup_slope")
                average_pressure_after = pretest_report.get("average_pressure_after")

            else:
                # No buildup found
                pretest_end_etim = None
                pretest_end_timestamp = None
                buildup_slope = None

            if average_pressure_after is None:
                average_pressure_after = {
                    "value": get_average(
                        event_list,
                        pressure_mnemonic,
                        reference_event_index - 10,
                        reference_event_index,
                    ),
                    "uom": get_uom(reference_event, pressure_mnemonic),
                }

            pretest_report.update(
                pretest_end_etim=pretest_end_etim,
                pretest_end_timestamp=pretest_end_timestamp,
                buildup_slope=buildup_slope,
                average_pressure_after=average_pressure_after,
            )

        if pretest_report and isinstance(pretest_report, dict):
            # Send data about the pretest as soon as we get it
            pretest_uid_base = "{event_type}-{probe_name}-{pretest_begin_timestamp}".format(
                **pretest_report
            )
            pretest_report.update(
                uid=md5(pretest_uid_base.encode("utf-8")).hexdigest(), __overwrite=["uid"]
            )
            event_sender(PRETEST_REPORT_EVENT_TYPE, pretest_report)

        if (state is PRETEST_STATES.INACTIVE) and pretest_report:
            # Clear the previous pretest data
            pretest_report = {}

    probe_data.update(process_state=state, pretest_report=pretest_report)


def find_drawdown(probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} starts to raise"""
    index_mnemonic = probe_data["index_mnemonic"]
    pretest_volume_mnemonic = probe_data["pretest_volume_mnemonic"]

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get("latest_seen_index", 0)
    valid_events = loop.filter_events(
        event_list, latest_seen_index, index_mnemonic, pretest_volume_mnemonic
    )

    # Before a drawdown, {pretest_volume_mnemonic} must be zero
    valid_events = list(
        dropwhile(lambda event: event.get(pretest_volume_mnemonic) > 0, valid_events)
    )

    # Check if the value was zero and has changed
    if valid_events:
        events_during_drawdown = list(
            dropwhile(lambda event: event.get(pretest_volume_mnemonic) == 0, valid_events)
        )
        is_drawdown = len(events_during_drawdown) > 0
    else:
        events_during_drawdown = []
        is_drawdown = False

    # There was a change.
    if is_drawdown:
        logging.info(
            ("Drawdown detected: {} -> {}.").format(valid_events[0], events_during_drawdown[0])
        )
        depth_mnemonic = probe_data["depth_mnemonic"]
        pressure_mnemonic = probe_data["pressure_mnemonic"]

        # Drawdown started at the first of these events
        reference_event = events_during_drawdown[0]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)
        pretest_begin_timestamp = reference_event.get("timestamp", timestamp.get_timestamp())

        message = (
            "Probe {}@{:.0f} ft: Drawdown started at {:.1f} s with pressure {:.2f} psi"
        )  # NOQA
        message_sender(
            message.format(probe_name, depth, etim, pressure), timestamp=pretest_begin_timestamp
        )

        detected_state = PRETEST_STATES.DRAWDOWN_START
        latest_seen_index = etim
        logging.info(
            "Probe {}: Pretest began at {:.0f}".format(probe_name, pretest_begin_timestamp)
        )
    else:
        detected_state = None
        pretest_begin_timestamp = None

    probe_data.update(
        latest_seen_index=latest_seen_index, pretest_begin_timestamp=pretest_begin_timestamp
    )
    return detected_state


def find_buildup(probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} stabilizes"""
    index_mnemonic = probe_data["index_mnemonic"]
    pretest_volume_mnemonic = probe_data["pretest_volume_mnemonic"]

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get("latest_seen_index", 0)
    valid_events = loop.filter_events(
        event_list, latest_seen_index, index_mnemonic, pretest_volume_mnemonic
    )

    # Check if the value is stable
    if len(valid_events) > 1:
        prev_event, last_event = valid_events[-2], valid_events[-1]

        last_pretest_volume = last_event.get(pretest_volume_mnemonic)
        prev_pretest_volume = prev_event.get(pretest_volume_mnemonic)
        drawdown_stopped = last_pretest_volume == prev_pretest_volume

        logging.info(
            ("End of drawdown detection: drawdown stopped={}; {} -> {}.").format(
                drawdown_stopped, prev_pretest_volume, last_pretest_volume
            )
        )
    else:
        drawdown_stopped = False

    if drawdown_stopped:
        depth_mnemonic = probe_data["depth_mnemonic"]
        pressure_mnemonic = probe_data["pressure_mnemonic"]

        # Find drawdown end
        events_after_drawdown = list(
            dropwhile(
                lambda event: event.get(pretest_volume_mnemonic) != last_pretest_volume,
                valid_events,
            )
        )

        # Drawdown finished at the first of these events
        reference_event = events_after_drawdown[0]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)
        drawdown_end_timestamp = reference_event.get("timestamp")

        message = "Probe {}@{:.0f} ft: Drawdown ended at {:.2f} s with pressure {:.2f} psi"  # NOQA
        message_sender(
            message.format(probe_name, depth, etim, pressure), timestamp=drawdown_end_timestamp
        )

        detected_state = PRETEST_STATES.DRAWDOWN_END
        latest_seen_index = etim
    else:
        detected_state = None
        drawdown_end_timestamp = None

    probe_data.update(
        latest_seen_index=latest_seen_index, drawdown_end_timestamp=drawdown_end_timestamp
    )
    return detected_state


def find_pump_recycle(probe_name, probe_data, event_list, message_sender):
    """State when {pretest_volume_mnemonic} returns to zero"""
    index_mnemonic = probe_data["index_mnemonic"]
    pretest_volume_mnemonic = probe_data["pretest_volume_mnemonic"]

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get("latest_seen_index", 0)
    valid_events = loop.filter_events(
        event_list, latest_seen_index, index_mnemonic, pretest_volume_mnemonic
    )

    # Before recycling the pump, {pretest_volume_mnemonic} must be higher than zero
    # So, we only care for the first zeroed event
    events_with_volume = list(
        dropwhile(lambda event: event.get(pretest_volume_mnemonic) > 0, valid_events)
    )
    is_reset = len(events_with_volume) > 0

    # There was a change.
    if is_reset:
        depth_mnemonic = probe_data["depth_mnemonic"]
        pressure_mnemonic = probe_data["pressure_mnemonic"]

        # Reset finished at the first of these events
        reference_event = events_with_volume[0]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)

        message = "Probe {}@{:.0f} ft: Pump reset at {:.1f} s with pressure {:.2f} psi"  # NOQA
        message_sender(
            message.format(probe_name, depth, etim, pressure),
            timestamp=reference_event.get("timestamp"),
        )

        detected_state = PRETEST_STATES.INACTIVE
        latest_seen_index = etim
    else:
        detected_state = None

    probe_data.update(latest_seen_index=latest_seen_index)
    return detected_state


def run_monitor(probe_name, probe_data, event_list, functions_map, settings):
    current_state = probe_data.get("process_state", PRETEST_STATES.INACTIVE)
    logging.debug("Pretest monitor for probe {} at state {}".format(probe_name, current_state))

    send_event = partial(raw.create, settings=settings)
    send_message = partial(messenger.send_message, settings=settings)
    create_annotation = partial(annotation.create, settings=settings)

    state_transition_func = functions_map[current_state]
    probe_data = loop.maybe_reset_latest_index(probe_data, event_list)
    detected_state = state_transition_func(
        probe_name, probe_data, event_list, message_sender=send_message
    )

    if (detected_state is None) and (current_state != PRETEST_STATES.INACTIVE):
        # Did the pretest volume get reset?
        detected_state = find_pump_recycle(
            probe_name, probe_data, event_list, message_sender=send_message
        )

    if detected_state and (detected_state != current_state):
        logging.info(
            "Pretest monitor for probe {}, {} -> {}".format(
                probe_name, current_state, detected_state
            )
        )
        current_state = detected_state
        maybe_create_annotation(
            probe_name, probe_data, current_state, annotation_func=create_annotation
        )

    maybe_update_pretest_report(
        probe_name, probe_data, current_state, event_list, event_sender=send_event
    )
    return current_state


def start(settings, task_id=None, **kwargs):
    if task_id:
        action = Action.continue_task(task_id=task_id)
    else:
        action = start_action(action_type="pretest_monitor")

    with action.context():
        setproctitle("DDA: Pretest monitor")
        logging.info("Pretest monitor started")

        functions_map = {
            PRETEST_STATES.INACTIVE: find_drawdown,
            PRETEST_STATES.DRAWDOWN_START: find_buildup,
            PRETEST_STATES.DRAWDOWN_END: partial(
                buildup.find_stable_buildup,
                targets={0.01: PRETEST_STATES.INACTIVE, 0.1: PRETEST_STATES.BUILDUP_STABLE},
                fallback_state=PRETEST_STATES.INACTIVE,
            ),
            PRETEST_STATES.BUILDUP_STABLE: partial(
                buildup.find_stable_buildup,
                targets={0.01: PRETEST_STATES.INACTIVE},
                fallback_state=PRETEST_STATES.INACTIVE,
            ),
        }

        monitor_settings = settings.get("monitor", {})
        window_duration = monitor_settings["window_duration"]
        target_probes = probes.init_data(settings)

        pretest_query = prepare_query(settings)
        span = f"last {window_duration} seconds"

        @on_event(pretest_query, settings, span=span, timeout=read_timeout)
        def handle_events(event, accumulator=None):
            def update_monitor_state(accumulator):
                for probe_name, probe_data in target_probes.items():
                    run_monitor(probe_name, probe_data, accumulator, functions_map, settings)

            process_event(event, update_monitor_state, settings, accumulator)

        handle_events(accumulator=[])

    action.finish()

    return
