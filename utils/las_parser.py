# -*- coding: utf-8 -*-
from multiprocessing import Pool
import time
import locale
from enum import Enum
import csv

import lasio

__all__ = [
    'events_from_las'
]


READ_MODES = Enum('READ_MODES', 'SINGLE_PASS, CONTINUOUS')


def delay_output(last_timestamp, next_timestamp, event_type=''):
    if last_timestamp == 0:
        sleep_time = 0
    else:
        sleep_time = max(next_timestamp - last_timestamp, 0)

    print("{}: Sleeping for {} seconds".format(event_type, sleep_time))
    time.sleep(sleep_time)


def read_next_frame(values_iterator, curves, curves_data, index_mnemonic):
    try:
        index, values = next(values_iterator)
        success = True
    except:
        output_frame = {}
        success = False

    if success:
        output_frame = {
            index_mnemonic: {'value': index, 'uom': 's'}
        }

        for index, channel in enumerate(curves):
            uom = curves_data.get(channel)
            channel_value = values[index]
            output_frame[channel] = {'value': channel_value, 'uom': uom}

    return success, output_frame


def read_metadata(las_data, settings):
    return {
        'well': las_data.well,
        'version': las_data.version,
        'params': las_data.params,
        'header': las_data.header,
    }


def open_las(source_settings, iterations, mode=READ_MODES.CONTINUOUS):
    path_list = source_settings['path_list']
    index_mnemonic = source_settings['index_mnemonic']

    if mode == 'round-robin':
        path_index = iterations % len(path_list)
    else:
        path_index = iterations

    try:
        path = path_list[path_index]
        data = lasio.read(path)
        success = True
    except Exception as e:
        data = e
        success = False

    return success, data, index_mnemonic


def export_curves_data(event_type, las_data, index_mnemonic, output_func, settings):
    print("Exporting curves for {}".format(event_type))
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

    print('File {} created'.format(output_filename))


def generate_events(event_type, las_data, index_mnemonic, output_func, settings):
    print("Generating events for {}".format(event_type))

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
            values_iterator, curves, curves_data, index_mnemonic
        )

        if success:
            next_timestamp = statuses.get(index_mnemonic, {}).get('value', 0)

            delay_output(last_timestamp, next_timestamp, event_type)
            output_func(event_type, statuses, settings)
            last_timestamp = next_timestamp

    print("Sleeping for 5 minutes between runs")
    time.sleep(60 * 5)


def process_source(event_type, source_settings, output_func, settings):
    debug_mode = settings.get('DEBUG', False)

    if debug_mode:
        read_mode = READ_MODES.SINGLE_PASS
        handling_func = export_curves_data
    else:
        read_mode = READ_MODES.CONTINUOUS
        handling_func = generate_events

    iterations = 0
    while True:
        success, las_data, index_mnemonic = open_las(
            source_settings,
            iterations,
            mode=read_mode
        )

        if success:
            handling_func(
                event_type,
                las_data,
                index_mnemonic,
                output_func,
                settings
            )
        elif read_mode == READ_MODES.SINGLE_PASS:
            break

        iterations += 1

    return


def events_from_las(output_func, settings):
    input_settings = settings.get('input', {})

    default_locale = locale.getlocale()
    locale.setlocale(locale.LC_ALL, ('en_US', 'UTF-8'))

    sources = input_settings.get('sources', {})
    num_sources = len(sources)

    with Pool(processes=num_sources) as pool:
        results = [
            pool.apply_async(
                process_source,
                (event_type, source_settings, output_func, settings)
            )
            for event_type, source_settings in sources.items()
        ]
        pool.close()
        pool.join()
        [item.wait() for item in results]

    locale.setlocale(locale.LC_ALL, default_locale)
