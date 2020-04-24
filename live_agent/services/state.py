# -*- coding: utf-8 -*-
import time
from hashlib import md5
from typing import Mapping, Dict, Union, AnyStr, Any

import dill
from live_client.utils import logging

__all__ = ["StateManager"]

number = Union[int, float]

TIMESTAMP_KEY = "__timestamp"


class StateManager(object):
    def __init__(self, name: AnyStr, delay_between_updates: number = 60):
        self.name = name
        self.delay_between_updates = delay_between_updates
        self.updated_at = 0

        if isinstance(name, str):
            name = bytes(name, "utf-8")

        self.identifier = md5(name).hexdigest()
        self.filename = f"/tmp/{self.identifier}.{name.decode('utf-8')}.live_agent"

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

    def save(self, state: Mapping[str, Any], force: bool = False) -> None:
        now = time.time()
        next_possible_update = self.updated_at + self.delay_between_updates
        time_until_update = next_possible_update - now

        if (time_until_update > 0) and (not force):
            logging.debug(f"Update for {self.identifier} dropped. Wait {time_until_update:.2f}s")
        else:
            self.do_save(state, timestamp=now)

        return

    def do_save(self, state: Mapping[str, Any], timestamp: number) -> None:
        state_filename = self.filename
        state.update(TIMESTAMP_KEY=timestamp)

        with open(state_filename, r"w+b") as f:
            dill.dump(state, f)

        self.updated_at = timestamp
        logging.debug(f"State for {self.identifier} saved")
