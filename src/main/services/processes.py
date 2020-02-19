# -*- coding: utf-8 -*-
from multiprocessing import Process
from eliot import start_action

from live_client.utils import logging
from .importer import load_process_handlers

__all__ = ["start"]


def filter_dict(source_dict, filter_func):
    return dict((key, value) for key, value in source_dict.items() if filter_func(key, value))


def resolve_process_handler(process_type, process_handlers):
    return process_handlers.get(process_type)


def get_processes(global_settings, process_handlers):
    processes = filter_dict(
        global_settings.get("processes", {}), lambda _k, v: v.get("enabled") is True
    )

    invalid_processes = filter_dict(
        processes, lambda _k, v: (v.get("type") not in process_handlers)
    )

    for name, info in invalid_processes.items():
        logging.error("Invalid process configured: {}, {}".format(name, info))

    valid_processes = filter_dict(processes, lambda name, _v: name not in invalid_processes)

    return valid_processes


def resolve_process_handlers(global_settings):
    process_handlers = load_process_handlers(global_settings)
    registered_processes = get_processes(global_settings, process_handlers)

    for name, settings in registered_processes.items():
        process_type = settings.pop("type")
        process_func = resolve_process_handler(process_type, process_handlers)
        settings.update(
            process_func=process_func,
            live=global_settings.get("live", {}),
            process_handlers=process_handlers,
        )

    return registered_processes


def start(global_settings):
    processes_to_run = resolve_process_handlers(global_settings)
    num_processes = len(processes_to_run)
    logging.info(
        "Starting {} processes: {}".format(num_processes, ", ".join(processes_to_run.keys()))
    )

    running_processes = []
    for name, settings in processes_to_run.items():
        process_func = settings.pop("process_func")

        with start_action(action_type=name) as action:
            task_id = action.serialize_task_id()
            process = Process(target=process_func, args=(settings, task_id))
            running_processes.append(process)
            process.start()

    return running_processes
