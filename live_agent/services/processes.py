# -*- coding: utf-8 -*-
from typing import Mapping, Iterable, Callable, Optional, Any
from multiprocessing import get_context as get_mp_context
from dataclasses import dataclass
from time import sleep

from eliot import Action, start_action
from live_client.utils import logging

from .importer import load_process_handlers
from .state import StateManager

__all__ = ["start", "agent_function"]


@dataclass
class ProcessSpec:
    function: Callable
    settings: Mapping
    process: Any


def filter_dict(source_dict: Mapping, filter_func: Callable) -> Mapping:
    return dict((key, value) for key, value in source_dict.items() if filter_func(key, value))


def resolve_process_handler(process_type: str, process_handlers: Mapping) -> Mapping:
    return process_handlers.get(process_type)


def get_processes(global_settings: Mapping, process_handlers: Mapping) -> Mapping:
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


def resolve_process_handlers(global_settings: Mapping):
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


def start(global_settings: Mapping) -> Iterable:
    processes_to_run = resolve_process_handlers(global_settings)
    num_processes = len(processes_to_run)
    logging.info(
        "Starting {} processes: {}".format(num_processes, ", ".join(processes_to_run.keys()))
    )

    process_map = {}
    for name, settings in processes_to_run.items():
        process_func = settings.pop("process_func")

        process_map[name] = ProcessSpec(
            function=agent_function(process_func, name=name, with_state=True),
            settings=settings,
            process=None,
        )

    return monitor_processes(process_map)


def monitor_processes(process_map: Mapping, heartbeat_interval: int = 60) -> Iterable:

    while True:
        for name, process_data in process_map.items():
            process = process_data.process

            if process and process.is_alive():
                logging.info(f'Process for "{name}" (pid={process.pid}) is alive')

            else:
                if process:
                    logging.info(f'Process for "{name}" (pid={process.pid}) has died. Restarting')
                else:
                    logging.info(f'Starting "{name}" using {process_data.function}')

                process = process_data.function(process_data.settings)
                try:
                    process.start()
                    logging.info(f'Process for "{name}" (pid={process.pid}) started')
                except OSError as e:
                    logging.exception(f"Error starting process {name} ({e})")

            process_data.process = process

        sleep(heartbeat_interval)

    running_processes = [item["process"] for item in process_map.values()]
    return running_processes


def agent_function(f: Callable, name: Optional[str] = None, with_state: bool = False) -> Callable:
    mp = get_mp_context("fork")

    def wrapped(*args, **kwargs):
        try:
            f_in_action = inside_action(f, name=name, with_state=with_state)
            return mp.Process(target=f_in_action, args=args, kwargs=kwargs)
        except Exception as e:
            logging.exception(f"Error during the execution of {f}: <{e}>")

    return wrapped


def inside_action(f: Callable, name: Optional[str] = None, with_state: bool = False) -> Callable:
    if name is None:
        name = f"{f.__module__}.{f.__name__}"

    def wrapped(*args, **kwargs):
        task_id = kwargs.get("task_id")
        if task_id:
            action = Action.continue_task(task_id=task_id)
        else:
            action = start_action(action_type=name)

        with action.context():
            task_id = action.serialize_task_id()
            kwargs["task_id"] = task_id
            if with_state:
                kwargs["state_manager"] = StateManager(name)

            try:
                return f(*args, **kwargs)
            except Exception as e:
                logging.exception(f"Error during the execution of {f}: <{e}>")

        action.finish()

    return wrapped
