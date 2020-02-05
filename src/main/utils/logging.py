# -*- coding: utf-8 -*-
from contextlib import contextmanager
from eliot import Action, start_action

__all__ = ["get_log_action"]


def get_log_action(task_id, action_type):
    if task_id:
        action = Action.continue_task(task_id=task_id)
    else:
        action = start_action(action_type=action_type)

    return action


@contextmanager
def manage_action(action):
    try:
        yield action
    finally:
        action.finish()
