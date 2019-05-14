# -*- coding: utf-8 -*-
import time
import logging
import requests


__all__ = [
    'notify_frequent_changes'
]


def await_next_request(sleep_time, process_name=''):
    logging.debug("{}: Sleeping for {} seconds".format(process_name, sleep_time))
    time.sleep(sleep_time)


def refresh_accumulator(flowrate_data, accumulator, index_mnemonic, window_duration):
    # Find out the latest timestamp received
    latest_value = flowrate_data[-1]
    latest_time = latest_value.get(index_mnemonic, 0)
    window_start = latest_time - window_duration

    # Purge old events and add the new ones
    purged_accumulator = [
        item for item in accumulator
        if item.get(index_mnemonic) > window_start
    ]
    purged_accumulator.extend(flowrate_data)
    return purged_accumulator, window_start, latest_time


def send_chat_message(message, process_settings, output_info, settings):
    destination_settings = process_settings['destination']
    output_func, output_settings = output_info

    output_settings.update(
        room=destination_settings['room'],
        author=destination_settings['author'],
    )
    output_func(message, output_settings)


def check_rate(flowrate_data, accumulator, process_settings, output_info, settings):
    monitor_settings = process_settings.get('monitor', {})
    index_mnemonic = monitor_settings['index_mnemonic']
    window_duration = monitor_settings['window_duration']

    # Calculate the number of changes per mnemonic during the window
    accumulator, begin, end = refresh_accumulator(
        flowrate_data, accumulator, index_mnemonic, window_duration
    )
    flowrate_mnemonics = monitor_settings['flowrate_mnemonics']
    change_counter = dict(
        (mnemonic, set())
        for mnemonic in flowrate_mnemonics
    )

    for event in accumulator:
        for mnemonic in flowrate_mnemonics:
            mnemonic_value = event.get(mnemonic)
            if mnemonic_value:
                change_counter[mnemonic].add(mnemonic_value)

    # Generate alerts whether the threshold was reached
    template = u'Whoa! {} was changed {} times over the last {} seconds, please calm down'

    max_threshold = monitor_settings['max_threshold']
    for mnemonic in flowrate_mnemonics:
        number_of_changes = len(change_counter[mnemonic])
        if number_of_changes > max_threshold:
            message = template.format(
                mnemonic, number_of_changes, int(end - begin)
            )
            send_chat_message(message, process_settings, output_info, settings)

    return accumulator


def notify_frequent_changes(process_name, process_settings, output_info, settings):
    logging.info("{}: Flowrate monitor started".format(process_name))
    session = requests.Session()
    accumulator = []

    url = process_settings['request']['url']
    interval = process_settings['request']['interval']

    iterations = 0
    while True:
        try:
            r = session.get(url)
            r.raise_for_status()

            flowrate_data = r.json()

            accumulator = check_rate(
                flowrate_data,
                accumulator,
                process_settings,
                output_info,
                settings
            )
            logging.info("{}: Request {} successful".format(
                process_name, iterations
            ))

        except Exception as e:
            logging.error(
                "{}: Error processing events during request {}, {}<{}>".format(
                    process_name, iterations, e, type(e)
                )
            )

        await_next_request(interval, process_name)
        iterations += 1

    return
