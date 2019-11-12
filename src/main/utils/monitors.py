# -*- coding: utf-8 -*-
import numpy as np
import queue

from eliot import Action, start_action
from functools import partial
from live_client.utils import timestamp, logging
from sklearn.linear_model import LinearRegression
from utils import loop

__all__ = ["find_slope", "find_stable_buildup", "get_function", "Monitor"]


def find_slope(
    process_name,
    event_list,
    index_mnemonic,
    value_mnemonic,
    targets=None,
    window_size=0,
    target_r=0,
):  # NOQA
    """
    State when the slope of the linear regression of {value_mnemonic}
    over {window_size} seconds is <= {target_slope}
    """
    target_slopes = sorted(targets)

    logging.debug(
        "{}: Trying to detect linear regression with a slope <= {}, watching {} events".format(
            process_name, ", ".join(str(item) for item in target_slopes), len(event_list)
        )
    )

    start_index = 0
    measured_slopes = []
    segment_found = []
    segment_slope = None
    r_score = None
    target_slope = None

    if event_list and targets:
        while True:
            segment_start = event_list[start_index][index_mnemonic]
            expected_end = segment_start + window_size

            segment_to_check = [
                item for item in event_list[start_index:] if item[index_mnemonic] <= expected_end
            ]
            segment_end = segment_to_check[-1][index_mnemonic]

            if (segment_end - segment_start) < (window_size * 0.9):
                logging.debug(
                    "{}: Not enough data, {} s of data available, {} s are needed".format(
                        process_name, (segment_end - segment_start), (window_size * 0.9)
                    )
                )
                break

            ##
            # do detection
            ##
            x = np.array([item.get(index_mnemonic) for item in segment_to_check]).reshape((-1, 1))
            y = np.array([item.get(value_mnemonic) for item in segment_to_check])

            model = LinearRegression().fit(x, y)
            if not model.coef_:
                continue

            segment_slope = abs(model.coef_[0])
            measured_slopes.append(segment_slope)

            matching_slopes = [item for item in target_slopes if segment_slope <= item]

            if matching_slopes:
                r_score = model.score(x, y)

            if matching_slopes and (r_score > target_r):
                # Return the slope, its score and the segment where it was found
                start_index = segment_to_check[0].get(index_mnemonic, -1)
                end_index = segment_to_check[-1].get(index_mnemonic, -1)

                target_slope = matching_slopes[0]
                segment_found = segment_to_check

                logging.info(
                    "{}: Linear regression within {} ({:.3f}, r²: {:.3f}) found between {:.2f} and {:.2f}".format(  # NOQA
                        process_name, target_slope, segment_slope, r_score, start_index, end_index
                    )
                )

                break
            else:
                start_index += 1

    if not segment_found:
        logging.debug(
            "{}: No segment found with slope within {}. Measured slopes were: {}".format(
                process_name, max(target_slopes), measured_slopes
            )
        )

    return {
        "segment": segment_found,
        "segment_slope": segment_slope,
        "r_score": r_score,
        "target_slope": target_slope,
        "measured_slopes": measured_slopes,
    }


def find_stable_buildup(
    process_name,
    probe_name,
    probe_data,
    event_list,
    message_sender,
    targets=None,
    fallback_state=None,
):  # NOQA
    """
    State when the slope of the linear regression of {pressure_mnemonic}
    over {buildup_duration} seconds is <= {target_slope}
    """
    index_mnemonic = probe_data["index_mnemonic"]
    pressure_mnemonic = probe_data["pressure_mnemonic"]
    depth_mnemonic = probe_data["depth_mnemonic"]
    buildup_duration = probe_data["buildup_duration"]
    buildup_wait_period = probe_data["buildup_wait_period"]
    target_r = probe_data.get("minimum_r2", 0.5)
    target_slopes = sorted(targets)
    detected_state = None

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = probe_data.get("latest_seen_index", 0)
    valid_events = loop.filter_events(
        event_list, latest_seen_index, index_mnemonic, pressure_mnemonic
    )

    logging.debug(
        "{}: Trying to detect a buildup with a slope <= {}, watching {} events".format(
            process_name, ", ".join(str(item) for item in target_slopes), len(valid_events)
        )
    )

    data = [
        {
            timestamp: item.get("timestamp"),
            index_mnemonic: item.get(index_mnemonic),
            pressure_mnemonic: item.get(pressure_mnemonic),
            depth_mnemonic: item.get(depth_mnemonic),
        }
        for item in valid_events
    ]

    regression_results = find_slope(
        process_name,
        data,
        index_mnemonic,
        pressure_mnemonic,
        targets=target_slopes,
        target_r=target_r,
        window_size=buildup_duration,
    )

    segment_found = regression_results.get("segment")
    pretest_end_timestamp = None
    target_state = None
    buildup_slope = None

    if segment_found:
        segment_slope = regression_results.get("segment_slope")
        r_score = regression_results.get("r_score")
        target_slope = regression_results.get("target_slope")
        target_state = targets[target_slope]

        # Use the last event of the segment as reference
        reference_event = segment_found[-1]
        etim = reference_event.get(index_mnemonic, -1)
        pressure = reference_event.get(pressure_mnemonic, -1)
        depth = reference_event.get(depth_mnemonic, -1)
        pretest_end_timestamp = reference_event.get("timestamp", timestamp.get_timestamp())

        message = (
            "Probe {}@{:.0f} ft: Buildup stabilized within {} ({:.3f}, r²: {:.3f}) at {:.2f} s with pressure {:.2f} psi"  # NOQA
        ).format(probe_name, depth, target_slope, segment_slope, r_score, etim, pressure)
        message_sender(process_name, message, timestamp=pretest_end_timestamp)

        detected_state = target_state
        latest_seen_index = etim
        buildup_slope = segment_slope
        logging.debug(message)

    elif data:
        measured_slopes = regression_results.get("measured_slopes", [])
        logging.debug(
            "{}: Buildup did not stabilize within {}. Measured slopes were: {}".format(
                process_name, max(target_slopes), measured_slopes
            )
        )

        # If a stable buildup takes too long, give up
        latest_event_index = data[-1].get(index_mnemonic)
        wait_period = latest_event_index - latest_seen_index
        depth = data[-1].get(depth_mnemonic, -1)
        if wait_period > buildup_wait_period:
            message = "Probe {}@{:.0f} ft: Buildup did not stabilize after {:.0f} s"  # NOQA
            message_sender(
                process_name,
                message.format(probe_name, depth, wait_period),
                timestamp=timestamp.get_timestamp(),
            )

            detected_state = fallback_state
            latest_seen_index = latest_event_index
            buildup_slope = None

    probe_data.update(
        latest_seen_index=latest_seen_index,
        pretest_end_timestamp=pretest_end_timestamp,
        buildup_slope=buildup_slope,
    )
    return detected_state


def get_monitor_parameters(settings, ignored_keys=None):
    monitor_settings = settings.get("monitor", {})
    if not ignored_keys:
        ignored_keys = ["probes", "mnemonics"]

    return dict((key, value) for key, value in monitor_settings.items() if key not in ignored_keys)


def get_global_mnemonics(settings):
    monitor_settings = settings.get("monitor", {})
    mnemonics = monitor_settings["mnemonics"]
    probe_prefix = "probe"

    filtered_mnemonics = dict(
        (f"{label} mnemonic", mnemonic)
        for label, mnemonic in mnemonics.items()
        if not label.startswith(probe_prefix)
    )
    global_mnemonics = dict(
        (label.replace(" ", "_"), mnemonic) for label, mnemonic in filtered_mnemonics.items()
    )
    return global_mnemonics


def get_probe_mnemonics(settings, probe_name):
    monitor_settings = settings.get("monitor", {})
    mnemonics = monitor_settings["mnemonics"]
    probe_prefix = f"probe{probe_name}"

    filtered_mnemonics = dict(
        (label.replace(probe_prefix, "").strip(), mnemonic)
        for label, mnemonic in mnemonics.items()
        if label.startswith(probe_prefix)
    )
    probe_mnemonics = dict(
        (label.replace(" ", "_"), mnemonic) for label, mnemonic in filtered_mnemonics.items()
    )
    return probe_mnemonics


def init_probes_data(settings):
    event_type = settings.get("event_type")
    monitor_settings = settings.get("monitor", {})
    probes = monitor_settings["probes"]

    return dict(
        (
            probe_name,
            dict(
                event_type=event_type,
                **get_monitor_parameters(settings),
                **get_global_mnemonics(settings),
                **get_probe_mnemonics(settings, probe_name),
            ),
        )
        for probe_name in probes
    )


def get_function(func_name, context):
    return context.get(
        func_name,
        lambda *args, **kwargs: logging.error(
            f"{func_name} not implemented: args={args}, kwargs={kwargs}"
        ),
    )


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


# TODO: Melhorar o nome da função abaixo: <<<<<
def get_log_action(task_id, action_type):
    if task_id:
        action = Action.continue_task(task_id=task_id)
    else:
        action = start_action(action_type=action_type)

    return action


class Monitor:
    """Base class to implement monitors"""

    def __init__(self, asset_name, settings, helpers=None, task_id=None):
        self.asset_name = asset_name
        self.settings = settings
        self.helpers = helpers
        self.task_id = task_id

        # Methods to wrap external functions:
        self.run_query = get_function("run_query", self.helpers)
        self.send_message = partial(
            get_function("send_message", self.helpers), extra_settings=self.settings
        )

    def start(self):
        raise NotImplementedError("Monitors must define a start method")
