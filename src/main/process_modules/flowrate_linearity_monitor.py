import queue
import traceback

from functools import partial
from live_client.utils import logging
from setproctitle import setproctitle
from utils import monitors

__all__ = ["start"]

READ_TIMEOUT = 120
MIN_FLOWRATE = 1e-18


def build_query(settings):
    monitor_settings = settings.get("monitor", {})
    flowrate_mnemonic = monitor_settings["flowrate_mnemonic"]
    pressure_mnemonic = monitor_settings["pressure_mnemonic"]
    sampling_interval = monitor_settings["sampling_interval"]
    window_duration = monitor_settings["window_duration"]
    threshold = monitor_settings["threshold"]

    # [TODO]:
    #   - A query abaixo relaciona apenas uma pressão com o flowrate. Na verdade
    # deveria relacionar uma diferença de pressão ou duas pressões (de modo a
    # calcular a diferença)
    query = f"""raw_well3
=> {flowrate_mnemonic}->value# as flowrate, {pressure_mnemonic}->value# as pressure
=> flowrate#, pressure#, flowrate#/pressure# as ratio
=> flowrate#,
    ratio#,
    avg(ratio) as mratio
   every {sampling_interval} seconds
   over last {window_duration} seconds
=> @filter(flowrate# > {MIN_FLOWRATE} & (abs(ratio#/mratio# - 1) > {threshold}))
"""
    print(query)
    return query


def check_rate(process_name, accumulator, settings, send_message):
    if not accumulator:
        return

    # Generate alerts whether the threshold was reached
    # a new event means another threshold breach
    latest_event = accumulator[-1]
    send_message(
        process_name,
        f'Ratio: {latest_event["ratio"]}, Mean: {latest_event["mratio"]}',
        timestamp=latest_event["timestamp"],
    )

    return accumulator


# TODO: Acrescentar validação dos dados lidos do arquivo json
def start(name, settings, helpers=None, task_id=None):
    process_name = f"{name} - flowrate linearity"

    action = monitors.get_log_action(task_id, "flowrate_linearity_monitor")
    with action.context():
        logging.info("{}: Flowrate linearity monitor started".format(process_name))
        setproctitle('DDA: Flowrate linearity monitor "{}"'.format(process_name))

        window_duration = settings["monitor"]["window_duration"]

        # Registrar consulta na API de console:
        run_query = monitors.get_function("run_query", helpers)
        results_process, results_queue = run_query(
            build_query(settings), span=f"last {window_duration} seconds", realtime=True
        )

        # Preparar callback para tratar os eventos vindos da API de console via response_queue:
        send_message = partial(
            monitors.get_function("send_message", helpers), extra_settings=settings
        )

        def process_events(accumulator):
            check_rate(process_name, accumulator, settings, send_message)

        try:
            monitors.handle_events(process_events, results_queue, settings, timeout=READ_TIMEOUT)

        except queue.Empty:
            # FIXME Não deveriamos chamar results_process.join() aqui? #<<<<<
            start(name, settings, helpers=helpers, task_id=task_id)

        except Exception as e:
            print(f"Ocorreu um erro: {e}")
            print("Stack trace:")
            traceback.print_exc()
            raise

    action.finish()
