# -*- coding: utf-8 -*-
import time
from hashlib import md5
from typing import Mapping, Dict, Any, TypeVar

import dill
from live_client.utils import logging

__all__ = ["StateManager"]

basestring = TypeVar("basestring", str, bytes)
number = TypeVar("number", int, float)

TIMESTAMP_KEY = "__timestamp"


class StateManager(object):
    def __init__(self, name: basestring, delay_between_updates: number = 60):
        self.name = name
        self.delay_between_updates = delay_between_updates
        self.updated_at = 0

        if isinstance(name, str):
            name = bytes(name, "utf-8")

        self.identifier = md5(name).hexdigest()
        self.filename = f"/tmp/{self.identifier}.live_agent"

    def load(self) -> Dict[str, Any]:
        state_filename = self.filename

        try:
            with open(state_filename, r"r+b") as f:
                state = dill.load(f)
        except Exception:
            state = {}

        self.updated_at = state.get(TIMESTAMP_KEY, self.updated_at)

        logging.info(f"State for {self.identifier} ({len(state)} keys) loaded")
        return state

    def save(self, state: Mapping[str, Any]) -> None:
        now = time.time()
        next_possible_update = self.updated_at + self.delay_between_updates
        time_until_update = next_possible_update - now

        if time_until_update <= 0:
            state_filename = self.filename
            state.update(TIMESTAMP_KEY=now)

            with open(state_filename, r"w+b") as f:
                dill.dump(state, f)

            self.updated_at = now
            logging.debug(f"State for {self.identifier} saved")
        else:
            logging.debug(
                f"State update for {self.identifier} dropped. Wait {time_until_update} seconds"
            )
        return
