# -*- coding: utf-8 -*-
import json
import logging
import os
import sys

from runner.daemon import Daemon
from utils import las_parser
from utils import raw_over_tcp, console_output

__all__ = []

PIDFILE_ENVVAR = 'PID_FILE'
DEFAULT_PIDFILE = "/var/run/live-replayer.pid"

LOGFILE_ENVVAR = 'LOG_FILE'
DEFAULT_LOG = "/var/log/live-replayer.log"


class EventFromImage(Daemon):

    def __init__(self, pidfile, settings_file):
        logfile = get_logfile()
        Daemon.__init__(self, pidfile, stdout=logfile, stderr=logfile)
        self.settings_file = settings_file

    def resolve_input_handler(self, settings):
        input_handlers = {
            'las_file': las_parser.events_from_las,
        }
        input_settings = settings.get('input', {})
        input_type = input_settings.get('type', 'las_file')
        return input_handlers.get(input_type)

    def resolve_output_handler(self, settings):
        output_handlers = {
            'raw_over_tcp': raw_over_tcp.format_and_send,
            'console': console_output.format_and_send,
        }
        output_settings = settings.get('output', {})
        output_type = output_settings.get('type', 'console')
        return output_handlers.get(output_type)

    def process_inputs(self, settings):
        input_func = self.resolve_input_handler(settings)
        output_func = self.resolve_output_handler(settings)

        return input_func(output_func, settings)

    def run(self):
        try:
            with open(self.settings_file, 'r') as fd:
                settings = json.load(fd)
                self.process_inputs(settings)
        except KeyboardInterrupt:
            logging.info('Execution interrupted')
            raise
        except:
            logging.exception('Error processing inputs')
            raise


def get_logfile():
    if LOGFILE_ENVVAR in os.environ:
        logfile = os.environ[LOGFILE_ENVVAR]
    else:
        logfile = DEFAULT_LOG

    return logfile


def configure_log(console=False):
    logfile = get_logfile()
    if console:
        logfile = '/dev/stdout'

    logging.basicConfig(
        filename=logfile,
        level=logging.INFO,
        format='%(asctime)-15s %(levelname)8s [%(module)s] %(message)s'
    )


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.stderr.write("Arguments: [console|start|stop|restart] [settings_file] \n")
        sys.exit(1)

    command = sys.argv[1]
    settings_file = sys.argv[2]

    if command not in ['console', 'start', 'stop', 'restart']:
        sys.stderr.write("Arguments: [console|start|stop|restart] [settings_file] \n")
        sys.exit(1)

    if not os.path.isfile(settings_file):
        sys.stderr.write("Settings file does not exist or is not a file\n")
        sys.exit(1)

    if PIDFILE_ENVVAR in os.environ:
        pidfile = os.environ[PIDFILE_ENVVAR]
    else:
        pidfile = DEFAULT_PIDFILE

    daemon = EventFromImage(pidfile, settings_file)

    configure_log(command == 'console')

    if command == 'console':
        logging.info('Starting on-console run')
        daemon.run()
    elif command == 'start':
        logging.info('A new START command was received')
        daemon.start()
    elif command == 'stop':
        logging.info('A new STOP command was received')
        daemon.stop()
    elif command == 'restart':
        logging.info('A new RESTART command was received')
        daemon.restart()
