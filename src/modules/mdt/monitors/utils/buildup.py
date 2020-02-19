# -*- coding: utf-8 -*-
import numpy as np
from sklearn.linear_model import LinearRegression

from live_client.utils import timestamp, logging

from . import loop

__all__ = ["find_stable_buildup"]


def find_stable_buildup(name, data, events, message_sender, targets=None, fallback_state=None):
    """
    State when the slope of the linear regression of {pressure_mnemonic}
    over {buildup_duration} seconds is <= {target_slope}
    """
    index_mnemonic = data["index_mnemonic"]
    pressure_mnemonic = data["pressure_mnemonic"]
    depth_mnemonic = data["depth_mnemonic"]
    buildup_duration = data["buildup_duration"]
    buildup_wait_period = data["buildup_wait_period"]
    target_r = data.get("minimum_r2", 0.5)
    target_slopes = sorted(targets)
    detected_state = None

    # In order to avoid detecting the same event twice we must trim the set of events
    # We also must ignore events without data
    latest_seen_index = data.get("latest_seen_index", 0)
    valid_events = loop.filter_events(events, latest_seen_index, index_mnemonic, pressure_mnemonic)

    logging.debug(
        "Trying to detect a buildup with a slope <= {}, watching {} events".format(
            ", ".join(str(item) for item in target_slopes), len(valid_events)
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
        ).format(name, depth, target_slope, segment_slope, r_score, etim, pressure)
        message_sender(message, timestamp=pretest_end_timestamp)

        detected_state = target_state
        latest_seen_index = etim
        buildup_slope = segment_slope
        logging.debug(message)

    elif data:
        measured_slopes = regression_results.get("measured_slopes", [])
        logging.debug(
            "Buildup did not stabilize within {}. Measured slopes were: {}".format(
                max(target_slopes), measured_slopes
            )
        )

        # If a stable buildup takes too long, give up
        latest_event_index = data[-1].get(index_mnemonic)
        wait_period = latest_event_index - latest_seen_index
        depth = data[-1].get(depth_mnemonic, -1)
        if wait_period > buildup_wait_period:
            message = "Probe {}@{:.0f} ft: Buildup did not stabilize after {:.0f} s"  # NOQA
            message_sender(
                message.format(name, depth, wait_period), timestamp=timestamp.get_timestamp()
            )

            detected_state = fallback_state
            latest_seen_index = latest_event_index
            buildup_slope = None

    data.update(
        latest_seen_index=latest_seen_index,
        pretest_end_timestamp=pretest_end_timestamp,
        buildup_slope=buildup_slope,
    )
    return detected_state


def find_slope(events, index_mnemonic, value_mnemonic, targets=None, window_size=0, target_r=0):
    """
    State when the slope of the linear regression of {value_mnemonic}
    over {window_size} seconds is <= {target_slope}
    """
    target_slopes = sorted(targets)

    logging.debug(
        "Trying to detect linear regression with a slope <= {}, watching {} events".format(
            ", ".join(str(item) for item in target_slopes), len(events)
        )
    )

    start_index = 0
    measured_slopes = []
    segment_found = []
    segment_slope = None
    r_score = None
    target_slope = None

    if events and targets:
        while True:
            segment_start = events[start_index][index_mnemonic]
            expected_end = segment_start + window_size

            segment_to_check = [
                item for item in events[start_index:] if item[index_mnemonic] <= expected_end
            ]
            segment_end = segment_to_check[-1][index_mnemonic]

            if (segment_end - segment_start) < (window_size * 0.9):
                logging.debug(
                    "Not enough data, {} s of data available, {} s are needed".format(
                        (segment_end - segment_start), (window_size * 0.9)
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
                    "Linear regression within {} ({:.3f}, r²: {:.3f}) found between {:.2f} and {:.2f}".format(  # NOQA
                        target_slope, segment_slope, r_score, start_index, end_index
                    )
                )

                break
            else:
                start_index += 1

    if not segment_found:
        logging.debug(
            "No segment found with slope within {}. Measured slopes were: {}".format(
                max(target_slopes), measured_slopes
            )
        )

    return {
        "segment": segment_found,
        "segment_slope": segment_slope,
        "r_score": r_score,
        "target_slope": target_slope,
        "measured_slopes": measured_slopes,
    }
