# -*- coding: utf-8 -*-
from functools import partial

from chatterbot.conversation import Statement  # NOQA

from live_client.assets import list_assets, fetch_asset_settings
from utils import logging

from .base_adapters import BaseBayesAdapter, WithStateAdapter
from .constants import (
    ASSET_LIST_EXAMPLES,
    ASSET_SELECTION_EXAMPLES,
    NEGATIVE_EXAMPLES,
    AUTO_ANALYSIS_EXAMPLES,
)


__all__ = [
    'AssetListAdapter',
    'AssetSelectionAdapter',
]

ITEM_PREFIX = '\n  '


class AssetListAdapter(BaseBayesAdapter, WithStateAdapter):
    """
    Interacts with the user to associate the chatbot to an asset
    """

    state_key = 'asset-list'
    default_state = {}
    positive_examples = ASSET_LIST_EXAMPLES
    negative_examples = NEGATIVE_EXAMPLES + ASSET_SELECTION_EXAMPLES + AUTO_ANALYSIS_EXAMPLES

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        available_assets = list_assets(
            kwargs['process_name'],
            kwargs['process_settings'],
            kwargs['output_info'],
        )

        if not available_assets:
            logging.warn(
                '{}: No assets available. Check permissions for this user!',
                kwargs['process_name']
            )

        self.load_state()
        self.state = {
            'assets': available_assets,
            'asset_names': [
                item.get('name')
                for item in available_assets
                if 'name' in item
            ]
        }
        self.share_state()

    def process(self, statement, additional_response_selection_parameters=None):
        self.confidence = self.get_confidence(statement)

        if self.confidence > self.confidence_threshold:
            response = Statement(
                text='The known assets are:{}{}'.format(
                    ITEM_PREFIX,
                    ITEM_PREFIX.join(self.state.get('asset_names', []))
                )
            )
            response.confidence = self.confidence

        else:
            response = None

        return response


class AssetSelectionAdapter(BaseBayesAdapter, WithStateAdapter):
    """
    Interacts with the user to associate the chatbot to an asset
    """

    state_key = 'live-asset'
    required_state = [
        'asset_id',
        'asset_name',
        'asset_config',
    ]
    default_state = {}
    positive_examples = ASSET_SELECTION_EXAMPLES
    negative_examples = NEGATIVE_EXAMPLES + ASSET_LIST_EXAMPLES + AUTO_ANALYSIS_EXAMPLES

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        process_name = kwargs['process_name']
        process_settings = kwargs['process_settings']
        output_info = kwargs['output_info']

        self.asset_fetcher = partial(
            fetch_asset_settings,
            process_name,
            process_settings,
            output_info
        )

    def only_enabled_curves(self, curves):
        idle_curve = [{}]

        return dict(
            (name, value) for (name, value) in curves.items()
            if value.get('options', idle_curve) != idle_curve
        )

    def process(self, statement, additional_response_selection_parameters=None):
        self.load_state()
        self.confidence = self.get_confidence(statement)

        def asset_was_mentioned(asset):
            return asset.get('name', 'INVALID ASSET NAME').lower() in statement.text.lower()

        if self.confidence > self.confidence_threshold:
            asset_list = self.shared_state.get('asset-list', {})
            selected_assets = list(
                filter(
                    asset_was_mentioned,
                    asset_list.get('assets', [{}])
                )
            )

            if len(selected_assets) == 1:
                selected_asset = selected_assets[0]

                asset_name = selected_asset.get('name')
                asset_id = selected_asset.get('id', 0)
                asset_type = selected_asset.get('asset_type', 'rig')
                asset_config = self.asset_fetcher(asset_id, asset_type=asset_type)

                self.state = {
                    'asset_id': asset_id,
                    'asset_name': asset_name,
                    'asset_config': asset_config,
                }
                self.share_state()

                event_type = asset_config.get('event_type', None)
                asset_curves = self.only_enabled_curves(asset_config.get('curves', {}))

                text_templ = 'Ok, the asset {} was selected. \nIt uses the event_type "{}" and has {} curves'
                response_text = text_templ.format(
                    selected_asset.get('name'),
                    event_type,
                    len(asset_curves.keys()),
                )

            elif len(selected_assets) > 1:
                response_text = "I didn't understand, which of there assets you chose?{}{}".format(
                    ITEM_PREFIX,
                    ITEM_PREFIX.join(item.get('name') for item in selected_assets)
                )

            else:
                response_text = "I didn't get the asset name. Can you repeat please?"

            response = Statement(text=response_text)
            response.confidence = self.confidence
        else:
            response = None

        return response
