import queue
import traceback

from functools import partial
from live_client.utils import logging
from setproctitle import setproctitle
from utils import monitors
from utils.search_engine import DuckFirstWordEngine, SearchResult

__all__ = ["start"]

READ_TIMEOUT = 120


class ProcessInfo:
    def __init__(self, process, queue):
        self.process = process
        self.queue = queue


class AlertReferenceMonitor:
    def __init__(self, name, settings, helpers=None, task_id=None):
        self.name = name
        self.settings = settings
        self.helpers = helpers
        self.task_id = task_id
        self.process_name = f"{name} - alert reference monitor"

        # Configuration:
        self.run_query = monitors.get_function("run_query", self.helpers)
        self.send_message = partial(
            monitors.get_function("send_message", self.helpers),
            extra_settings=self.settings
        )


    def start(self):
        action = monitors.get_log_action(self.task_id, "alert_reference_monitor")
        with action.context():
            logging.info("{}: Alert Reference Monitor".format(self.process_name))
            setproctitle('DDA: Alert Reference Monitor "{}"'.format(self.process_name))

            # Registrar consulta por anotações na API de console:
            results_process, results_queue = self.run_query(
                self.build_query(),
                span="last day",
                realtime=True
            )
            handle_process_queue(
                self.process_annotation,
                ProcessInfo(results_process, results_queue),
                self
            )

            results_process.join()

        action.finish()


    def build_query(self):
        return "__annotations __src:rulealert"


    def process_annotation(self, event):
        annotation_message = event["message"]

        engine = DuckFirstWordEngine()
        results = engine.search(annotation_message)
        message_lines = [f'References found for query "{annotation_message}":']
        if len(results) > 0:
            res = results[0]
            message_lines.append(f'<{res.url}|{res.desc}>')
        else:
            message_lines.append('No result found')
        message = '\n'.join(message_lines)

        self.send_message(
            self.process_name,
            f'{message}',
            timestamp=event["timestamp"],
        )


def start(name, settings, helpers=None, task_id=None):
    m = AlertReferenceMonitor(name, settings, helpers, task_id)
    m.start()


def handle_process_queue(processor, pinfo, context):
    try:
        monitors.handle_events(
            processor_func = process_accumulator_last_result(processor),
            results_queue = pinfo.queue,
            settings = context.settings,
            timeout=READ_TIMEOUT
        )

    except queue.Empty:
        pinfo.process.join(1)
        start(**context.__dict__)

    except Exception as e:
        # TODO: Dar tratamento adequado abaixo: <<<<<
        print(f"Ocorreu um erro: {e}")
        print("Stack trace:")
        traceback.print_exc()
        raise


def process_accumulator_last_result(processor):
    def process(accumulator):
        latest_event = accumulator[-1]
        processor(latest_event)
        return accumulator
    return process
