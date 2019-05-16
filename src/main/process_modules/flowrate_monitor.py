# -*- coding: utf-8 -*-
import logging
import requests

from utils import loop


__all__ = [
    'start'
]


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


def check_rate(process_name, flowrate_data, accumulator, process_settings, output_info, settings):
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
    latest_changes = dict(
        (mnemonic, 0)
        for mnemonic in flowrate_mnemonics
    )

    for event in accumulator:
        for mnemonic in flowrate_mnemonics:
            index = event.get(index_mnemonic)
            mnemonic_value = event.get(mnemonic)
            if mnemonic_value:
                change_counter[mnemonic].add("{:.1f}".format(mnemonic_value))
                latest_changes[mnemonic] = index

    # Generate alerts whether the threshold was reached
    # and the most recent change was in the latest batch of events
    template = u'Whoa! {} was changed {} times over the last {} seconds, please calm down ({})'

    max_threshold = monitor_settings['max_threshold']
    interval = process_settings['request']['interval']
    interval_start = end - interval

    for mnemonic in flowrate_mnemonics:
        number_of_changes = len(change_counter[mnemonic])
        latest_change = latest_changes[mnemonic]
        if (number_of_changes > max_threshold) and (latest_change > interval_start):
            message = template.format(
                mnemonic,
                number_of_changes,
                int(end - begin),
                ', '.join(change_counter[mnemonic])
            )
            send_chat_message(message, process_settings, output_info, settings)
            logging.info("{}: Sending message '{}'".format(
                process_name, message
            ))

    return accumulator


def start(process_name, process_settings, output_info, settings):
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
                process_name,
                flowrate_data,
                accumulator,
                process_settings,
                output_info,
                settings
            )
            logging.debug("{}: Request {} successful".format(
                process_name, iterations
            ))

        except Exception as e:
            logging.error(
                "{}: Error processing events during request {}, {}<{}>".format(
                    process_name, iterations, e, type(e)
                )
            )

        loop.await_next_cycle(interval, process_name)
        iterations += 1

    return
