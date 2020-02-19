# -*- coding: utf-8 -*-
from functools import partial
from eliot import Action, start_action

from live_client.events import messenger

__all__ = ["Monitor"]


class Monitor:
    """Base class to implement monitors"""

    monitor_name = "base_monitor"

    def __init__(self, settings, task_id=None, **kwargs):
        self.settings = settings
        self.task_id = task_id

        self.send_message = partial(messenger.send_message, settings=settings)

    def run(self):
        raise NotImplementedError("Monitors must define a start method")

    @classmethod
    def start(cls, settings, task_id=None, **kwargs):
        if task_id:
            action = Action.continue_task(task_id=task_id)
        else:
            action = start_action(action_type=cls.monitor_name)

        with action.context():
            monitor = cls(settings, task_id=task_id, **kwargs)
            monitor.run()
