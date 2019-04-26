# -*- coding: utf-8 -*-
import time
import lasio

__all__ = [
    'events_from_las'
]


def delay_output(last_timestamp, next_timestamp):
    if last_timestamp == 0:
        sleep_time = 0
    else:
        sleep_time = max(next_timestamp - last_timestamp, 0)

    print("Sleeping for {} seconds".format(sleep_time))
    time.sleep(sleep_time)


def read_next_frame(values_iterator, curves, curves_data, time_mnemonic):
    try:
        index, values = next(values_iterator)
        success = True
    except:
        success = False

    output_frame = {
        time_mnemonic: {'value': index, 'uom': 's'}
    }

    for index, channel in enumerate(curves):
        uom = curves_data.get(channel)

        try:
            channel_value = values[index]
        except Exception as e:
            import pdb
            pdb.set_trace()
            pass
            e

        output_frame[channel] = {'value': channel_value, 'uom': uom}

    return success, output_frame


def open_las(settings):
    input_settings = settings.get('input', {})
    path = input_settings['path']
    time_mnemonic = input_settings['time_mnemonic']

    try:
        data = lasio.read(path)
        success = True
    except Exception as e:
        data = e
        success = False

    return success, data, time_mnemonic


def events_from_las(output_func, settings):
    while True:
        success, las_data, time_mnemonic = open_las(settings)
        curves_data = dict(
            (item.mnemonic, item.unit)
            for item in las_data.curves
        )
        las_df = las_data.df()
        values_iterator = las_df.iterrows()
        curves = las_df.columns

        last_timestamp = 0
        while success:
            success, statuses = read_next_frame(
                values_iterator, curves, curves_data, time_mnemonic
            )

            if success:
                next_timestamp = statuses.get(time_mnemonic, {}).get('value', 0)

                delay_output(last_timestamp, next_timestamp)
                output_func(statuses, settings)
                last_timestamp = next_timestamp

        print("Sleeping for 60 seconds between runs")
        time.sleep(60)
