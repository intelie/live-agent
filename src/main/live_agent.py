# -*- coding: utf-8 -*-
import os
import sys
import signal
import json

from eliot import start_action, to_file, Action
from setproctitle import setproctitle

from live_client.utils import logging
from services.daemon import Daemon
from services import processes

__all__ = []

PIDFILE_ENVVAR = "DDA_PID_FILE"
DEFAULT_PIDFILE = "/var/run/live-agent.pid"

LOGFILE_ENVVAR = "DDA_LOG_FILE"
DEFAULT_LOG = "/var/log/live-agent.log"


class LiveAgent(Daemon):
    def __init__(self, pidfile, settings_file):
        setproctitle("DDA:  Main process")
        logfile = get_logfile()
        error_logfile = f"{logfile}.error"

        with start_action(action_type="init_daemon") as action:
            task_id = action.serialize_task_id()
            Daemon.__init__(self, pidfile, stdout=logfile, stderr=error_logfile, task_id=task_id)

        self.settings_file = settings_file

    def run(self):
        with Action.continue_task(task_id=self.task_id):
            try:
                with open(self.settings_file, "r") as fd:
                    global_settings = json.load(fd)

                logging_settings = global_settings.get("logging")
                live_settings = global_settings.get("live")

                logging.setup_python_logging(logging_settings)
                logging.setup_live_logging(logging_settings, live_settings)

                processes.start(global_settings)
            except KeyboardInterrupt:
                logging.info("Execution interrupted")
                raise
            except Exception:
                logging.exception("Error processing inputs")
                raise


def init_worker():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def get_logfile():
    if LOGFILE_ENVVAR in os.environ:
        logfile = os.environ[LOGFILE_ENVVAR]
    else:
        logfile = DEFAULT_LOG

    return logfile


def configure_log():
    log_file = get_logfile()
    to_file(open(log_file, "ab"))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.stderr.write("Arguments: [console|start|stop|restart] [settings_file] \n")
        sys.exit(1)

    command = sys.argv[1]
    settings_file = sys.argv[2]

    if command not in ["console", "start", "stop", "restart"]:
        sys.stderr.write("Arguments: [console|start|stop|restart] [settings_file] \n")
        sys.exit(1)

    if not os.path.isfile(settings_file):
        sys.stderr.write("Settings file does not exist or is not a file\n")
        sys.exit(1)

    if PIDFILE_ENVVAR in os.environ:
        pidfile = os.environ[PIDFILE_ENVVAR]
    else:
        pidfile = DEFAULT_PIDFILE

    daemon = LiveAgent(pidfile, settings_file)

    configure_log()

    if command == "console":
        logging.info("Starting on-console run")
        daemon.run()
    elif command == "start":
        logging.info("A new START command was received")
        daemon.start()
    elif command == "stop":
        logging.info("A new STOP command was received")
        daemon.stop()
    elif command == "restart":
        logging.info("A new RESTART command was received")
        daemon.restart()
