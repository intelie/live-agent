from eliot import start_action  # NOQA
from multiprocessing import active_children
from chatterbot.conversation import Statement

from live_client.utils import logging

from live_agent.services.processes import agent_function
from ..src.actions import CallbackAction
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
    positive_examples = ["start", "run", "monitor", "monitors"]
    description = "Start the monitors"
    usage_example = "start the monitors"

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)
        self.room_id = kwargs.get("room_id")
        self.settings = kwargs.get("settings", {})
        self.process_handlers = self.settings.get("process_handlers")
        self.all_monitors = self.settings.get("monitors", {})

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
        active_monitors = dict((item.name, item) for item in active_children() if item.name)
        active_monitors = self._start_monitors(selected_asset, active_monitors)

        if len(active_monitors) == 0:
            response_text = f'{selected_asset["asset_name"]} has no registered monitors'
        else:
            monitor_names = list(active_monitors.keys())
            response_text = "{} monitors running ({})".format(
                len(monitor_names), ", ".join(monitor_names)
            )

            self.state = {"active_monitors": monitor_names}
            self.share_state()

        return response_text

    def _start_monitors(self, selected_asset, active_monitors):
        asset_name = self.get_asset_name(selected_asset)
        asset_monitors = self.all_monitors.get(asset_name, {})

        monitors_to_start = dict(
            (name, settings)
            for (name, settings) in asset_monitors.items()
            if not ((name in active_monitors) and (active_monitors[name].is_alive()))
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
            monitor_settings["live"] = self.settings["live"]
            monitor_settings["output"]["room"] = {"id": self.room_id}

            logging.debug(f"Starting {name}")
            try:
                process_func = self.process_handlers.get(process_type)
                process_func = agent_function(process_func, name=name, with_state=True)
                process = process_func(monitor_settings, name=name)
                active_monitors[name] = process
                process.start()

            except Exception as e:
                logging.warn(f"Error starting {name}: {e}")

        return active_monitors
