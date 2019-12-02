from eliot import start_action  # NOQA
from multiprocessing import Process

from dda.chatbot.actions import CallbackAction, ShowTextAction
from live_client.utils import logging
from process_modules import PROCESS_HANDLERS

from .base import BaseBayesAdapter, WithAssetAdapter
from ..constants import get_positive_examples, get_negative_examples


__all__ = ["MonitorControlAdapter"]

"""
TODO:

1. definir formato das configurações
2. implementar controle para parada dos monitores
3. implementar detecção de dados insuficientes
4. implementar controles individuais para os monitores
"""

ITEM_PREFIX = "\n  "


class MonitorControlAdapter(BaseBayesAdapter, WithAssetAdapter):
    """
    Controls the monitors for an assets
    """

    state_key = "monitor-control"
    required_state = ["assetId"]
    default_state = {"active_monitors": {}}
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        self.process_settings = kwargs["process_settings"]
        self.helpers = dict(
            (name, func)
            for (name, func) in kwargs.get("functions", {}).items()
            if "_state" not in name
        )

        self.all_monitors = self.process_settings.get("monitors", {})

    def start_monitors(self, selected_asset, active_monitors):
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
                logging.info(f"{asset_name}: Ignoring disabled process '{name}'")
                continue

            process_type = monitor_settings.get("type")
            if process_type not in PROCESS_HANDLERS:
                logging.error(f"{asset_name}: Ignoring unknown process type '{process_type}'")
                continue

            monitor_settings["event_type"] = self.get_event_type(selected_asset)
            process_func = PROCESS_HANDLERS.get(process_type)
            with start_action(action_type=name) as action:
                task_id = action.serialize_task_id()
                process = Process(
                    target=process_func,
                    args=(asset_name, monitor_settings),
                    kwargs={"helpers": self.helpers, "task_id": task_id},
                )
                active_monitors[name] = process
                process.start()

        return active_monitors

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)

        if confidence > self.confidence_threshold:
            self.load_state()
            active_monitors = self.state.get("active_monitors")
            selected_asset = self.get_selected_asset()

            if not selected_asset:
                response = ShowTextAction(
                    "No asset selected. Please select an asset first.", confidence
                )
            else:
                response = CallbackAction(
                    self.handle_start_monitors,
                    confidence=1,
                    selected_asset=selected_asset,
                    active_monitors=active_monitors,
                )
        else:
            response = None

        return response

    def handle_start_monitors(self, selected_asset, active_monitors):
        active_monitors = self.start_monitors(selected_asset, active_monitors)

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
