# -*- coding: utf-8 -*-
from live_client.utils import timestamp, logging

from utils import loop, monitors

__all__ = ["find_stable_buildup"]


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

    regression_results = monitors.find_slope(
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
