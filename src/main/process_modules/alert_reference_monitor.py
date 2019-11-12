import queue
import traceback

from live_client.utils import logging
from setproctitle import setproctitle
from utils import monitors
from utils.search_engine import DuckFirstWordEngine

__all__ = ["start"]

READ_TIMEOUT = 120


# TODO: Mover para o arquivo adequado
class ProcessInfo:
    def __init__(self, process, queue):
        self.process = process
        self.queue = queue


class AlertReferenceMonitor(monitors.Monitor):
    def __init__(self, asset_name, settings, helpers=None, task_id=None):
        super().__init__(asset_name, settings, helpers, task_id)

        self.process_name = f"{self.asset_name} - alert reference monitor"
        self.span = settings["monitor"].get("span")

    def start(self):
        action = monitors.get_log_action(self.task_id, "alert_reference_monitor")
        with action.context():
            logging.info("{}: Alert Reference Monitor".format(self.process_name))
            setproctitle('DDA: Alert Reference Monitor "{}"'.format(self.process_name))

            # Registrar consulta por anotações na API de console:
            results_process, results_queue = self.run_query(
                self.build_query(), span=self.span, realtime=True
            )
            handle_process_queue(
                self.process_annotation, ProcessInfo(results_process, results_queue), self
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
            message_lines.append(f"<{res.url}|{res.desc}>")
        else:
            message_lines.append("No result found")
        message = "\n".join(message_lines)

        self.send_message(self.process_name, f"{message}", timestamp=event["timestamp"])


def start(asset_name, settings, helpers=None, task_id=None):
    m = AlertReferenceMonitor(asset_name, settings, helpers, task_id)
    m.start()


def handle_process_queue(processor, pinfo, context):
    try:
        monitors.handle_events(
            processor_func=process_accumulator_last_result(processor),
            results_queue=pinfo.queue,
            settings=context.settings,
            timeout=READ_TIMEOUT,
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
