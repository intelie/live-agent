# -*- coding: utf-8 -*-
import logging
from enum import Enum
import csv

import lasio

from output_modules import raw, messenger
from utils import loop, timestamp

__all__ = [
    'start'
]


READ_MODES = Enum('READ_MODES', 'SINGLE_PASS, CONTINUOUS')


def send_message(process_name, message, timestamp, process_settings=None, output_info=None):
    messenger.maybe_send_message_event(
        process_name,
        message,
        timestamp,
        process_settings=process_settings,
        output_info=output_info
    )
    messenger.maybe_send_chat_message(
        process_name,
        message,
        process_settings=process_settings,
        output_info=output_info
    )


def delay_output(last_timestamp, next_timestamp, event_type=''):
    if last_timestamp == 0:
        sleep_time = 0
    else:
        sleep_time = max(next_timestamp - last_timestamp, 0)

    loop.await_next_cycle(sleep_time, event_type)


def read_next_frame(event_type, values_iterator, curves, curves_data, index_mnemonic):
    try:
        index, values = next(values_iterator)
        success = True
    except Exception as e:
        output_frame = {}
        success = False
        logging.debug("{}: Error reading next value, {}<{}>".format(event_type, e, type(e)))

    if success:
        output_frame = {
            index_mnemonic: {'value': index, 'uom': 's'}
        }

        for index, channel in enumerate(curves):
            uom = curves_data.get(channel)
            channel_value = values[index]
            output_frame[channel] = {'value': channel_value, 'uom': uom}

    return success, output_frame


def open_las(process_settings, iterations, mode=READ_MODES.CONTINUOUS):
    path_list = process_settings['path_list']
    index_mnemonic = process_settings['index_mnemonic']

    if mode == READ_MODES.CONTINUOUS:
        path_index = iterations % len(path_list)
    else:
        path_index = iterations

    try:
        path = path_list[path_index]
        with open(path, 'r') as las_file:
            data = lasio.read(las_file)

        success = True
        logging.debug("Success opening file {}>".format(path))
    except Exception as e:
        data = e
        success = False
        logging.error("Error opening file {}, {}<{}>".format(path, e, type(e)))

    return success, data, index_mnemonic


def export_curves_data(event_type, las_data, index_mnemonic, process_settings, output_info, settings):
    logging.info("Exporting curves for {}".format(event_type))
    output_dir = settings.get('temp_dir', '/tmp')

    source_name = las_data.version.SOURCE.value
    output_filename = '{}/{}.csv'.format(output_dir, source_name)

    with open(output_filename, 'w') as output_file:
        writer = csv.writer(output_file)

        for curve in las_data.curves:
            writer.writerow([
                '{} - {}'.format(curve.mnemonic, curve.descr),
                curve.mnemonic,
                curve.unit,
                '',
                ''
            ])

    logging.info('File {} created'.format(output_filename))


def generate_events(event_type, las_data, index_mnemonic, process_settings, output_info, settings):
    logging.info("{}: Event generation started".format(event_type))
    connection_func, output_settings = output_info

    source_name = las_data.version.SOURCE.value
    curves_data = dict(
        (item.mnemonic, item.unit)
        for item in las_data.curves
    )
    las_df = las_data.df()
    values_iterator = las_df.iterrows()
    curves = las_df.columns

    success = True
    last_timestamp = 0
    while success:
        success, statuses = read_next_frame(
            event_type, values_iterator, curves, curves_data, index_mnemonic
        )

        if success:
            next_timestamp = statuses.get(index_mnemonic, {}).get('value', 0)

            delay_output(last_timestamp, next_timestamp, event_type)
            if last_timestamp == 0:
                message = "Replay from '{}' started at TIME {}".format(source_name, next_timestamp)
                send_message(
                    event_type,
                    message,
                    timestamp.get_timestamp(),
                    process_settings=process_settings,
                    output_info=output_info
                )

            raw.format_and_send(event_type, statuses, output_settings, connection_func=connection_func)
            last_timestamp = next_timestamp


def start(process_name, process_settings, output_info, settings):
    debug_mode = settings.get('DEBUG', False)
    event_type = process_settings['destination']['event_type']

    if debug_mode:
        read_mode = READ_MODES.SINGLE_PASS
        handling_func = export_curves_data
    else:
        read_mode = READ_MODES.CONTINUOUS
        handling_func = generate_events

    iterations = 0
    while True:
        try:
            success, las_data, index_mnemonic = open_las(
                process_settings,
                iterations,
                mode=read_mode
            )

            if success:
                handling_func(
                    event_type,
                    las_data,
                    index_mnemonic,
                    process_settings,
                    output_info,
                    settings,
                )
                logging.info("{}: Iteration {} successful".format(
                    event_type, iterations
                ))

            elif read_mode == READ_MODES.SINGLE_PASS:
                logging.info("{}: Single pass mode, exiting".format(event_type))
                break
            else:
                raise las_data

            loop.await_next_cycle(
                60 * 5,
                event_type,
                message="Sleeping for 5 minutes between runs",
                log_func=logging.info
            )

        except KeyboardInterrupt:
            logging.info(
                "{}: Stopping after {} iterations".format(
                    event_type, iterations
                )
            )
            raise

        except Exception as e:
            logging.error(
                "{}: Error processing events during iteration {}, {}<{}>".format(
                    event_type, iterations, e, type(e)
                )
            )

        iterations += 1

    return
