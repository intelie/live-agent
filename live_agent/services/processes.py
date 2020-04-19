# -*- coding: utf-8 -*-
from typing import Mapping, Iterable, Callable, Optional
from multiprocessing import get_context as get_mp_context

from eliot import Action, start_action
from live_client.utils import logging

from .importer import load_process_handlers
from .state import StateManager

__all__ = ["start", "agent_function"]


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

    running_processes = []
    for name, settings in processes_to_run.items():
        with start_action(action_type=name) as action:
            process_func = settings.pop("process_func")
            process_func = agent_function(process_func, name=name, with_state=True)

            task_id = action.serialize_task_id()
            process = process_func(settings, task_id=task_id)
            running_processes.append(process)
            process.start()

    return running_processes


def agent_function(f: Callable, name: Optional[str] = None, with_state: bool = False) -> Callable:
    mp = get_mp_context("fork")
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
                return mp.Process(target=f, args=args, kwargs=kwargs)
            except Exception as e:
                logging.exception(f"Error during the execution of {f}: <{e}>")

        action.finish()

    return wrapped
