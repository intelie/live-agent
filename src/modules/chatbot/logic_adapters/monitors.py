from eliot import start_action  # NOQA
from multiprocessing import Process
from chatterbot.conversation import Statement

from live_client.utils import logging

from chatbot.actions import CallbackAction
from .base import BaseBayesAdapter, WithAssetAdapter

__all__ = ["MonitorControlAdapter"]

"""
TODO:

1. definir formato das configurações
2. implementar controle para parada dos monitores
3. implementar detecção de dados insuficientes
4. implementar controles individuais para os monitores
"""


class MonitorControlAdapter(BaseBayesAdapter, WithAssetAdapter):
    """
    Controls the monitors for an assets
    """

    state_key = "monitor-control"
    required_state = ["assetId"]
    default_state = {"active_monitors": {}}
    positive_examples = ["start monitor", "run monitor"]
    description = "Start the monitors"
    usage_example = "start the monitors"

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)
        self.process_settings = kwargs.get("process_settings", {})
        self.process_handlers = self.process_settings.get("process_handlers")

        self.helpers = dict(
            (name, func)
            for (name, func) in kwargs.get("functions", {}).items()
            if "_state" not in name
        )

        self.all_monitors = self.process_settings.get("monitors", {})

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)

        if confidence > self.confidence_threshold:
            self.load_state()
            active_monitors = self.state.get("active_monitors")
            selected_asset = self.get_selected_asset()

            if not selected_asset:
                response = Statement(text="No asset selected. Please select an asset first.")
                response.confidence = confidence
            else:
                response = CallbackAction(
                    self.execute_action,
                    selected_asset=selected_asset,
                    active_monitors=active_monitors,
                    confidence=confidence,
                )
        else:
            response = None

        return response

    def execute_action(self, selected_asset, active_monitors):
        active_monitors = self._start_monitors(selected_asset, active_monitors)

        if active_monitors == {}:
            response_text = f'{selected_asset["asset_name"]} has no registered monitors'
        else:
            self.state = {"active_monitors": active_monitors}
            self.share_state()

            monitor_names = list(active_monitors.keys())
            response_text = "{} monitors running ({})".format(
                len(monitor_names), ", ".join(monitor_names)
            )

        return response_text

    def _start_monitors(self, selected_asset, active_monitors):
        asset_name = self.get_asset_name(selected_asset)
        asset_monitors = self.all_monitors.get(asset_name, {})

        monitors_to_start = dict(
            (name, settings)
            for (name, settings) in asset_monitors.items()
            if (name not in active_monitors) or not (active_monitors[name].is_alive())
        )

        for name, settings in monitors_to_start.items():
            monitor_settings = settings.copy()
            is_enabled = monitor_settings.get("enabled", False)
            if not is_enabled:
                logging.info(f"Ignoring disabled process '{name}'")
                continue

            process_type = monitor_settings.get("type")
            if process_type not in self.process_handlers:
                logging.error(f"Ignoring unknown process type '{process_type}'")
                continue

            monitor_settings["event_type"] = self.get_event_type(selected_asset)
            process_func = self.process_handlers.get(process_type)

            monitor_settings["live"] = self.process_settings["live"]

            with start_action(action_type=name) as action:
                logging.debug(f"Starting {name}")
                task_id = action.serialize_task_id()
                try:
                    process = Process(
                        target=process_func, args=(monitor_settings,), kwargs={"task_id": task_id}
                    )
                    active_monitors[name] = process
                    process.start()

                except Exception as e:
                    logging.warn(f"Error starting {name}: {e}")

        return active_monitors
