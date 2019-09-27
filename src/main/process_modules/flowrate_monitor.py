# -*- coding: utf-8 -*-
import requests
from setproctitle import setproctitle
from eliot import Action

from live_client.events import messenger
from live_client.utils import logging
from utils import loop


__all__ = [
    'start'
]


def check_rate(process_name, flowrate_data, accumulator, process_settings, output_info):
    monitor_settings = process_settings.get('monitor', {})
    index_mnemonic = monitor_settings['index_mnemonic']
    window_duration = monitor_settings['window_duration']

    # Calculate the number of changes per mnemonic during the window
    accumulator, begin, end = loop.refresh_accumulator(
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
            messenger.maybe_send_chat_message(
                process_name,
                message,
                process_settings,
                output_info
            )

    return accumulator


def start(process_name, process_settings, output_info, task_id):
    with Action.continue_task(task_id=task_id):
        logging.info("{}: Flowrate monitor started".format(process_name))
        setproctitle('DDA: Flowrate monitor')
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
