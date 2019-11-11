import queue
import traceback

from functools import partial
from live_client.utils import logging
from setproctitle import setproctitle
from utils import monitors
from utils.search_engine import DuckEngine, SearchResult

__all__ = ["start"]

READ_TIMEOUT = 120

class TaskContext:
    def __init__(self, name, settings, helpers, taskid):
        self.name = name
        self.settings = settings
        self.helpers = helpers
        self.taskid = taskid


class ProcessInfo:
    def __init__(self, process, queue):
        self.process = process
        self.queue = queue


def build_query(settings):
    query = "annotations __src:rulealert"
    return query

funcs = {}

def analyze_annotation(event):
    send_message = funcs['send_message']
    print('!!! Alert Search Executing !!!')
    print(f'Source: {event["__src"]}')
    annotation_message = event["message"]

    engine = DuckEngine()
    results = engine.search(annotation_message)
    message_lines = [f'References found for query "{annotation_message}":']
    if len(results) > 0:
        res = results[0]
        message_lines.append(f'<{res.url}|{res.desc}>')
    else:
        message_lines.append('No result found')
    message = '\n'.join(message_lines)

    print(f'Message: {message}')
    send_message(
        '!Nome do processo!',
        f'{message}',
        timestamp=event["timestamp"],
    )


def start(name, settings, helpers=None, task_id=None):
    process_name = f"{name} - alert reference search"

    action = monitors.get_log_action(task_id, "alert_reference_monitor")
    with action.context():
        logging.info("{}: Reference search monitor".format(process_name))
        setproctitle('DDA: Reference search monitor "{}"'.format(process_name))

        # Configuration:
        run_query = monitors.get_function("run_query", helpers)
        send_message = partial(
            monitors.get_function("send_message", helpers),
            extra_settings=settings
        )
        funcs['send_message'] = send_message

        # Registrar consulta por anotações na API de console:
        results_process, results_queue = run_query(
            "__annotations __src:rulealert",
            #span="last day", #<<<<<
            realtime=True
        )
        #handle_process_queue(analyze_annotation, results_queue, helpers, task_id)
        handle_process_queue(
            analyze_annotation,
            ProcessInfo(results_process, results_queue),
            TaskContext(name, settings, helpers, task_id)
        )
        results_process.join()

    action.finish()


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
        print(f'Accumulator: {accumulator} !!!!!!!!!!') #<<<<<
        latest_event = accumulator[-1]
        processor(latest_event)
        return accumulator
    return process
