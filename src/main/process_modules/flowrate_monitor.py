# -*- coding: utf-8 -*-
from functools import partial
import queue
from setproctitle import setproctitle

from live_client.utils import logging
from utils import monitors


__all__ = ["start"]

read_timeout = 120
request_timeout = (3.05, 5)
max_retries = 5


def check_rate(process_name, accumulator, settings, send_message):
    if not accumulator:
        return

    # Generate alerts whether the threshold was reached
    # a new event means another threshold breach
    template = "Whoa! {} was changed {} times over the last {} seconds, please calm down ({})"
    latest_event = accumulator[-1]
    message = template.format(
        latest_event["mnemonic"],
        int(latest_event["num_changes"]),
        int((int(latest_event["end"]) - int(latest_event["start"])) / 1000),
        latest_event["values_list"],
    )
    send_message(process_name, message, timestamp=latest_event["timestamp"])

    return accumulator


def build_query(settings):
    event_type = settings.get("event_type")
    monitor_settings = settings.get("monitor", {})
    max_threshold = monitor_settings["max_threshold"]
    window_duration = monitor_settings["window_duration"]
    sampling_frequency = monitor_settings["sampling_frequency"]
    precision = monitor_settings["precision"]

    flowrate_mnemonics = monitor_settings["flowrate_mnemonics"]
    mnemonics_list = "|".join(flowrate_mnemonics)

    query = f"""
        {event_type} mnemonic!:({mnemonics_list})
        => value as current_value,
           value#:round({precision}):dcount() as num_changes,
           value#round({precision}):set() as values_list,
           timestamp:min() as start,
           timestamp:max() as end,
           mnemonic
          by mnemonic
          every {sampling_frequency} seconds over last {window_duration} seconds
        => @filter(num_changes >= {max_threshold})
        => @throttle 1, {window_duration} seconds
    """
    logging.debug(f'query is "{query}"')

    return query


def start(name, settings, helpers=None, task_id=None):
    process_name = f"{name} - flowrate"

    action = monitors.get_log_action(task_id, "flowrate_monitor")
    with action.context():
        logging.info("{}: Flowrate monitor started".format(process_name))
        setproctitle('DDA: Flowrate monitor "{}"'.format(process_name))

        window_duration = settings["monitor"]["window_duration"]

        # Registrar consulta na API de console:
        run_query = monitors.get_function("run_query", helpers)
        results_process, results_queue = run_query(
            build_query(settings), span=f"last {window_duration} seconds", realtime=True
        )

        # Preparar callback para tratar os eventos vindos da API de console via response_queue:
        send_message = partial(
            monitors.get_function("send_message", helpers), extra_settings=settings
        )

        def process_events(accumulator):
            check_rate(process_name, accumulator, settings, send_message)

        try:
            monitors.handle_events(process_events, results_queue, settings, timeout=read_timeout)
        except queue.Empty:
            # [ECS]: Essa chamada é um problema pois python não faz tail recursion <<<<<
            start(name, settings, helpers=helpers, task_id=task_id)

    action.finish()
