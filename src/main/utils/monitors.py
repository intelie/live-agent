# -*- coding: utf-8 -*-
import logging

import numpy as np
from sklearn.linear_model import LinearRegression

__all__ = ['find_slope']


def find_slope(process_name, event_list, index_mnemonic, value_mnemonic, targets=None, window_size=0, target_r=0):
    """
    State when the slope of the linear regression of {value_mnemonic}
    over {window_size} seconds is <= {target_slope}
    """
    target_slopes = sorted(targets)

    logging.debug("{}: Trying to detect linear regression with a slope <= {}, watching {} events".format(
        process_name,
        ', '.join(str(item) for item in target_slopes),
        len(event_list)
    ))

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
                item for item in event_list[start_index:]
                if item[index_mnemonic] <= expected_end
            ]
            segment_end = segment_to_check[-1][index_mnemonic]

            if (segment_end - segment_start) < (window_size * 0.9):
                logging.debug("{}: Not enough data, {} s of data available, {} s are needed".format(
                    process_name, (segment_end - segment_start), (window_size * 0.9)
                ))
                break

            ##
            # do detection
            ##
            x = np.array([
                item.get(index_mnemonic) for item in segment_to_check
            ]).reshape((-1, 1))
            y = np.array([
                item.get(value_mnemonic) for item in segment_to_check
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

            if matching_slopes and (r_score > target_r):
                # Return the slope, its score and the segment where it was found
                start_index = segment_to_check[0].get(index_mnemonic, -1)
                end_index = segment_to_check[-1].get(index_mnemonic, -1)

                target_slope = matching_slopes[0]
                segment_found = segment_to_check

                logging.info(
                    "{}: Linear regression within {} ({:.3f}, r²: {:.3f}) found between {:.2f} and {:.2f}".format(
                        process_name,
                        target_slope,
                        segment_slope,
                        r_score,
                        start_index,
                        end_index
                    )
                )

                break
            else:
                start_index += 1

    if not segment_found:
        logging.debug("{}: No segment found with slope within {}. Measured slopes were: {}".format(
            process_name, max(target_slopes), measured_slopes
        ))

    return {
        'segment': segment_found,
        'segment_slope': segment_slope,
        'r_score': r_score,
        'target_slope': target_slope,
        'measured_slopes': measured_slopes,
    }
