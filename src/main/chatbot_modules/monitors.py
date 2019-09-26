# -*- coding: utf-8 -*-
from chatterbot.conversation import Statement
from eliot import start_action  # NOQA
from multiprocessing import Process

from live_client.utils import logging
from process_modules import PROCESS_HANDLERS
from .base_adapters import BaseBayesAdapter, WithAssetAdapter
from .constants import get_positive_examples, get_negative_examples


__all__ = ['MonitorControlAdapter']

ITEM_PREFIX = '\n  '


class MonitorControlAdapter(BaseBayesAdapter, WithAssetAdapter):
    """
    Controls the monitors for an assets
    """

    state_key = 'monitor-control'
    required_state = [
        'assetId',
    ]
    default_state = {
        'active_monitors': {}
    }
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        self.process_settings = kwargs['process_settings']
        self.output_info = kwargs['output_info']
        self.room_id = kwargs['room_id']  # NOQA

        self.all_monitors = self.process_settings.get('monitors', {})

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)

        if confidence > self.confidence_threshold:
            self.load_state()
            selected_asset = self.get_selected_asset()

            if selected_asset:
                asset_name = self.get_asset_name(selected_asset)
                asset_monitors = self.all_monitors.get(asset_name)
                if asset_monitors:
                    active_monitors = {}

                    for name, process_settings in asset_monitors.items():
                        is_enabled = process_settings.get('enabled', False)
                        if not is_enabled:
                            logging.info(f"Ignoring disabled process '{name}'")
                            continue

                        process_type = process_settings.get('type')
                        if process_type not in PROCESS_HANDLERS:
                            logging.error(f"Ignoring unknown process type '{process_type}'")
                            continue

                        process_func = PROCESS_HANDLERS.get(process_type)
                        with start_action(action_type=name) as action:
                            task_id = action.serialize_task_id()
                            process = Process(
                                target=process_func,
                                args=(
                                    name,
                                    process_settings,
                                    self.output_info,
                                    {},
                                    task_id
                                )
                            )
                            active_monitors[name] = process_settings
                            process.start()

                    self.state = {'active_monitors': active_monitors}
                    self.share_state()
                    response_text = "Monitors {} started".format(
                        ', '.join(active_monitors.keys())
                    )
                    confidence = 1

                else:
                    response_text = f'{selected_asset} has no registered monitors'

            else:
                response_text = "No asset selected. Please select an asset first."

            response = Statement(text=response_text)
            response.confidence = confidence
        else:
            response = None

        return response
