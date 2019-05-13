# -*- coding: utf-8 -*-
import json
import logging
import os
import sys
from multiprocessing import Pool

from runner.daemon import Daemon
from utils import las_parser
from utils import raw_over_tcp, console_output

__all__ = []

PIDFILE_ENVVAR = 'PID_FILE'
DEFAULT_PIDFILE = "/var/run/live-agent.pid"

LOGFILE_ENVVAR = 'LOG_FILE'
DEFAULT_LOG = "/var/log/live-agent.log"


class LiveAgent(Daemon):

    def __init__(self, pidfile, settings_file):
        logfile = get_logfile()
        Daemon.__init__(self, pidfile, stdout=logfile, stderr=logfile)
        self.settings_file = settings_file

    def get_output_options(self, settings):
        output_settings = settings.get('output', {})
        destinations = output_settings.get('destinations', {})
        return destinations

    def get_input_sources(self, settings, output_options):
        input_settings = settings.get('input', {})
        sources = input_settings.get('sources', {})
        for item in sources.values():
            assert(item.get('destination') in output_options)

        return sources

    def resolve_handlers(self, input_sources, output_options):
        output_funcs = dict(
            (name, (self.resolve_output_handler(out_settings), out_settings))
            for name, out_settings in output_options.items()
        )

        for name, in_settings in input_sources.items():
            input_type = in_settings.pop('type')
            output_type = in_settings.pop('destination')
            in_settings.update(
                input_func=self.resolve_input_handler(input_type),
                output=output_funcs.get(output_type)
            )

        return input_sources

    def resolve_input_handler(self, input_type):
        input_handlers = {
            'las_file': las_parser.events_from_las,
        }
        return input_handlers.get(input_type)

    def resolve_output_handler(self, output_settings):
        output_handlers = {
            'raw_over_tcp': raw_over_tcp.format_and_send,
            'console': console_output.format_and_send,
        }
        output_type = output_settings.get('type')
        return output_handlers.get(output_type)

    def process_inputs(self, settings):
        output_options = self.get_output_options(settings)
        input_sources = self.get_input_sources(settings, output_options)

        resolved_sources = self.resolve_handlers(input_sources, output_options)
        num_sources = len(resolved_sources)

        pool = Pool(processes=num_sources)
        results = []
        for name, source_settings in resolved_sources.items():
            input_func = source_settings.pop('input_func')
            output_info = source_settings.pop('output')

            results.append(
                pool.apply_async(
                    input_func,
                    (name, source_settings, output_info, settings)
                )
            )

        pool.close()
        pool.join()
        return [item.wait() for item in results]

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

    daemon = LiveAgent(pidfile, settings_file)

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
