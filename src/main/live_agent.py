# -*- coding: utf-8 -*-
import json
import logging
import os
import sys
from multiprocessing import Pool

from runner.daemon import Daemon
from process_modules import PROCESS_HANDLERS
from output_modules import OUTPUT_HANDLERS
from utils.filter import filter_dict

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

    def resolve_process_handler(self, process_type):
        return PROCESS_HANDLERS.get(process_type)

    def resolve_output_handler(self, output_settings):
        output_type = output_settings.get('type')
        return OUTPUT_HANDLERS.get(output_type)

    def get_output_options(self, settings):
        destinations = settings.get('output', {})
        invalid_destinations = dict(
            (name, out_settings)
            for name, out_settings in destinations.items()
            if out_settings.get('type') not in OUTPUT_HANDLERS
        )

        for name, info in invalid_destinations.items():
            logging.error("Invalid output configured: {}, {}".format(
                name, info
            ))

        return destinations

    def get_processes(self, settings, output_options):
        processes = filter_dict(
            settings.get('processes', {}),
            lambda _k, v: v.get('enabled') is True
        )

        invalid_processes = filter_dict(
            processes,
            lambda _k, v: (
                (v.get('type') not in PROCESS_HANDLERS) or
                (v.get('destination', {}).get('name') not in output_options)
            )
        )

        for name, info in invalid_processes.items():
            logging.error("Invalid process configured: {}, {}".format(
                name, info
            ))

        valid_processes = filter_dict(
            processes,
            lambda name, _v: name not in invalid_processes
        )

        return valid_processes

    def resolve_handlers(self, settings):
        output_options = self.get_output_options(settings)
        registered_processes = self.get_processes(settings, output_options)

        output_funcs = dict(
            (name, (self.resolve_output_handler(out_settings), out_settings))
            for name, out_settings in output_options.items()
        )

        for name, process_settings in registered_processes.items():
            process_type = process_settings.pop('type')
            output_type = process_settings['destination']['name']
            process_settings.update(
                process_func=self.resolve_process_handler(process_type),
                output=output_funcs.get(output_type)
            )

        return registered_processes

    def start_processes(self, settings):
        processes_to_run = self.resolve_handlers(settings)
        num_processes = len(processes_to_run)
        logging.info('Starting {} processes: {}'.format(
            num_processes, ', '.join(processes_to_run.keys())
        ))

        if num_processes > 1:
            results = []
            pool = Pool(processes=num_processes)
            for name, process_settings in processes_to_run.items():
                process_func = process_settings.pop('process_func')
                output_info = process_settings.pop('output')

                results.append(
                    pool.apply_async(
                        process_func,
                        (name, process_settings, output_info, settings)
                    )
                )

            pool.close()
            pool.join()
            result = [item.wait() for item in results]
        else:
            for name, process_settings in processes_to_run.items():
                process_func = process_settings.pop('process_func')
                output_info = process_settings.pop('output')

                result = process_func(name, process_settings, output_info, settings)

        return result

    def run(self):
        try:
            with open(self.settings_file, 'r') as fd:
                settings = json.load(fd)
                self.start_processes(settings)
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
    python_version = sys.version_info.major

    log_level = logging.INFO
    log_file = get_logfile()
    log_format = '%(asctime)-15s %(levelname)8s [%(module)s] %(message)s'

    if python_version == 3:
        if console:
            handlers = [logging.StreamHandler()]
        else:
            handlers = [logging.FileHandler(log_file)]

        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=handlers,
        )
    else:
        if console:
            log_file = '/dev/stdout'

        logging.basicConfig(
            level=log_level,
            format=log_format,
            filename=log_file,
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
