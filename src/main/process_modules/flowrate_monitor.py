# -*- coding: utf-8 -*-
from functools import partial
import queue
from setproctitle import setproctitle
from eliot import Action, start_action

from live_client.utils import logging
from utils import monitors


__all__ = [
    'start'
]

read_timeout = 120
request_timeout = (3.05, 5)
max_retries = 5


def check_rate(process_name, accumulator, settings, send_message):
    if not accumulator:
        return

    monitor_settings = settings.get('monitor', {})
    flowrate_mnemonic = monitor_settings['flowrate_mnemonic']
    latest_event = accumulator[-1]

    # Generate alerts whether the threshold was reached
    # a new event means another threshold breach
    interval = (latest_event['end'] - latest_event['start']) / 1000
    template = (
        u'Whoa! {} was changed {} times over the last {} seconds, please calm down ({})'
    )
    message = template.format(
        flowrate_mnemonic,
        latest_event['num_changes'],
        interval,
        latest_event['values_list'],
    )
    send_message(settings, message)

    return accumulator


def build_query(settings):
    event_type = settings.get('event_type')
    monitor_settings = settings.get('monitor', {})
    flowrate_mnemonic = monitor_settings['flowrate_mnemonic']
    max_threshold = monitor_settings['max_threshold']
    window_duration = monitor_settings['window_duration']
    sampling_frequency = monitor_settings['sampling_frequency']
    precision = monitor_settings['precision']

    query = f"""
        {event_type} mnemonic!:{flowrate_mnemonic}
        => value as current_value,
           value#:round({precision}):dcount() as num_changes,
           value#round({precision}):set() as values_list,
           timestamp:min() as start,
           timestamp:max() as end,
          every {sampling_frequency} seconds over last {window_duration} seconds
        => @filter(num_changes >= {max_threshold})
        => @throttle 1, {window_duration} seconds
    """
    logging.debug(f'query is "{query}"')

    return query


def start(name, settings, helpers=None, task_id=None):
    process_name = f"{name} - pretest"

    if task_id:
        action = Action.continue_task(task_id=task_id)
    else:
        action = start_action(action_type='flowrate_monitor')

    with action.context():
        logging.info("{}: Flowrate monitor started".format(process_name))
        setproctitle('DDA: Flowrate monitor "{}"'.format(process_name))

        functions_map = {
            'send_message': partial(
                monitors.get_function('send_message', helpers),
                extra_settings=settings,
            ),
            'create_annotation': partial(
                monitors.get_function('create_annotation', helpers),
                extra_settings=settings,
            ),
            'run_query': monitors.get_function(
                'run_query', helpers
            ),
        }

        monitor_settings = settings.get('monitor', {})
        window_duration = monitor_settings['window_duration']

        results_process, results_queue = functions_map.get('run_query')(
            build_query(settings),
            span=f"last {window_duration} seconds",
            realtime=True,
        )

        def process_events(accumulator):
            check_rate(
                process_name,
                accumulator,
                settings,
                functions_map.get('send_message'),
            )

        try:
            monitors.handle_events(
                process_events,
                results_queue,
                settings,
                timeout=read_timeout
            )
        except queue.Empty:
            start(name, settings, helpers=helpers, task_id=task_id)

    action.finish()

    return
