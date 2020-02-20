from setproctitle import setproctitle

from live_client.utils import logging
from live_client.query import on_event
from live_client.events import messenger
from live.utils.query import handle_events as process_event

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
    return query


def check_rate(accumulator, settings):
    if not accumulator:
        return

    # Generate alerts whether the threshold was reached
    # a new event means another threshold breach
    latest_event = accumulator[-1]
    messenger.send_message(
        f'Ratio: {latest_event["ratio"]}, Mean: {latest_event["mratio"]}',
        timestamp=latest_event["timestamp"],
        settings=settings,
    )

    return accumulator


# TODO: Acrescentar validação dos dados lidos do arquivo json
def start(settings, task_id=None, **kwargs):
    logging.info("Flowrate linearity monitor started")
    setproctitle("DDA: Flowrate linearity monitor")

    window_duration = settings["monitor"]["window_duration"]

    fl_query = build_query(settings)
    span = f"last {window_duration} seconds"

    @on_event(fl_query, settings, span=span, timeout=READ_TIMEOUT)
    def handle_events(event, accumulator=None):
        def update_monitor_state(accumulator):
            check_rate(accumulator, settings)

        process_event(event, update_monitor_state, settings, accumulator)

    handle_events(accumulator=[])
