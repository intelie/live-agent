# -*- coding: utf-8 -*-
import os
import signal
import json

from eliot import start_action, to_file, Action
from setproctitle import setproctitle

from live_client.utils import logging
from .services import processes, daemon

__all__ = ["LiveAgent"]

PIDFILE_ENVVAR = "DDA_PID_FILE"
DEFAULT_PIDFILE = "/var/run/live-agent.pid"

LOGFILE_ENVVAR = "DDA_LOG_FILE"
DEFAULT_LOG = "/var/log/live-agent.log"


class LiveAgent(daemon.Daemon):
    def __init__(self, pidfile, settings_file):
        setproctitle("DDA:  Main process")
        self.configure_log()
        self.settings_file = settings_file

        with start_action(action_type="init_daemon") as action:
            task_id = action.serialize_task_id()
            error_logfile = f"{self.logfile}.error"
            return super().__init__(
                pidfile, stdout=self.logfile, stderr=error_logfile, task_id=task_id
            )

    def run(self):
        with Action.continue_task(task_id=self.task_id):
            try:
                with open(self.settings_file, "r") as fd:
                    global_settings = json.load(fd)

                logging_settings = global_settings.get("logging")
                live_settings = global_settings.get("live")

                logging.setup_python_logging(logging_settings)
                logging.setup_live_logging(logging_settings, live_settings)

                agent_processes = processes.start(global_settings)
            except KeyboardInterrupt:
                logging.info("Execution interrupted")
                raise
            except Exception:
                logging.exception("Error processing inputs")
                raise

        for item in agent_processes:
            item.terminate()
            item.join()

    @property
    def logfile(self):
        return os.environ.get(LOGFILE_ENVVAR, DEFAULT_LOG)

    def configure_log(self):
        to_file(open(self.logfile, "ab"))


def init_worker():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
