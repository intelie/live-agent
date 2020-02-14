# -*- coding: utf-8 -*-
import numpy as np

from functools import partial
from live_client.utils import logging
from live_client.events import messenger
from sklearn.linear_model import LinearRegression

__all__ = ["find_slope", "get_function", "Monitor"]


def find_slope(event_list, index_mnemonic, value_mnemonic, targets=None, window_size=0, target_r=0):
    """
    State when the slope of the linear regression of {value_mnemonic}
    over {window_size} seconds is <= {target_slope}
    """
    target_slopes = sorted(targets)

    logging.debug(
        "Trying to detect linear regression with a slope <= {}, watching {} events".format(
            ", ".join(str(item) for item in target_slopes), len(event_list)
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


def get_function(func_name, context):
    return context.get(
        func_name,
        lambda *args, **kwargs: logging.error(
            f"{func_name} not implemented: args={args}, kwargs={kwargs}"
        ),
    )


class Monitor:
    """Base class to implement monitors"""

    def __init__(self, settings, task_id=None, **kwargs):
        self.settings = settings
        self.task_id = task_id

        self.send_message = partial(messenger.send_message, settings=settings)

    def run(self):
        raise NotImplementedError("Monitors must define a start method")
