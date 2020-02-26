# -*- coding: utf-8 -*-
import os
import time
from hashlib import md5
from typing import Mapping, Dict, Any, TypeVar

import dill
from live_client.utils import logging
from eliot import Action

__all__ = ["StateManager"]

basestring = TypeVar("basestring", str, bytes)


class StateManager(object):
    def __init__(self, name: basestring, task_id: bytes):
        self.name = name
        if isinstance(name, str):
            name = bytes(name, "utf-8")

        self.identifier = md5(name).hexdigest()
        self.filename = f"/tmp/{self.identifier}.live_agent"
        self.action = Action.continue_task(task_id=task_id)

    def load(self) -> Dict[str, Any]:
        with self.action.context():
            state_filename = self.filename

            if os.path.isfile(state_filename) and (os.path.getsize(state_filename) > 0):
                with open(state_filename, r"r+b") as f:
                    state = dill.load(f)
            else:
                state = {}

        logging.info(f"State for {self.identifier} ({len(state)} keys) loaded")
        return state

    def save(self, state: Mapping[str, Any]) -> None:
        with self.action.context():
            state_filename = self.filename
            state.update(__timestamp=time.time())

            with open(state_filename, r"w+b") as f:
                dill.dump(state, f)

        logging.debug(f"State for {self.identifier} saved")
        return
