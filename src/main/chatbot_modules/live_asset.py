# -*- coding: utf-8 -*-
from chatterbot.conversation import Statement  # NOQA

from live_client.assets import list_assets
from utils import logging

from .base_adapters import BaseBayesAdapter, WithStateAdapter


__all__ = [
    'AssetListAdapter',
    'AssetSelectionAdapter',
]


LIST_EXAMPLES = [
    "which assets exist",
    "list the assets",
    "list which assets exist",
    "show the assets",
    "show the asset list",
    "show which assets exist",
    "display the assets",
    "display the asset list",
    "display which assets exist",
]
SELECTION_EXAMPLES = [
    "set as the active asset",
    "set as the current asset",
    "set this room's asset to",
    "update this room's asset to",
    "the current asset is",
    "the new asset is",
    "update the asset is",
    "change the asset to",
]
ITEM_PREFIX = '\n  '


class AssetListAdapter(BaseBayesAdapter, WithStateAdapter):
    """
    Interacts with the user to associate the chatbot to an asset
    """

    state_key = 'asset-list'
    default_state = {}
    positive_examples = LIST_EXAMPLES
    negative_examples = [
        'what is the value',
        'hey what value does it',
        'do you know the value',
        'do you know what is the value',
        'it is time to go to sleep',
        'what is your favorite color',
        'what the color of the sky',
        'i had a great time',
        'thyme is my favorite herb',
        'do you have time to look at my essay',
        'how do you have the time to do all this'
        'what is it'
    ] + SELECTION_EXAMPLES

    def __init__(self, chatbot, **kwargs):
        self.env = kwargs.pop('env', {})
        super().__init__(chatbot, **kwargs)

        available_assets = list_assets(
            self.env['process_name'],
            self.env['process_settings'],
            self.env['output_info'],
        )

        if not available_assets:
            logging.warn(
                '{}: No assets available. Check permissions for this user!',
                self.env['process_name']
            )

        self.state = {
            'assets': available_assets,
            'asset_names': [
                item.get('name')
                for item in available_assets
                if 'name' in item
            ]
        }

    def process(self, statement, additional_response_selection_parameters=None):
        default_response = super().process(
            statement,
            additional_response_selection_parameters=additional_response_selection_parameters
        )

        if self.confidence > self.confidence_threshold:

            response = Statement(
                text='The known assets are:{}{}'.format(
                    ITEM_PREFIX,
                    ITEM_PREFIX.join(self.state.get('asset_names', []))
                )
            )
            response.confidence = self.confidence
            self.share_state(additional_response_selection_parameters)
        else:
            response = default_response

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
    positive_examples = SELECTION_EXAMPLES
    negative_examples = [
        'what is the value',
        'hey what value does it',
        'do you know the value',
        'do you know what is the value',
        'it is time to go to sleep',
        'what is your favorite color',
        'what the color of the sky',
        'i had a great time',
        'thyme is my favorite herb',
        'do you have time to look at my essay',
        'how do you have the time to do all this'
        'what is it'
    ] + LIST_EXAMPLES

    def __init__(self, chatbot, **kwargs):
        self.env = kwargs.pop('env', {})
        super().__init__(chatbot, **kwargs)

    def process(self, statement, additional_response_selection_parameters=None):
        self.load_state(additional_response_selection_parameters)

        default_response = super().process(
            statement,
            additional_response_selection_parameters=additional_response_selection_parameters
        )
        response = default_response

        if self.confidence > self.confidence_threshold:

            def asset_was_mentioned(asset):
                return asset.get('name', 'INVALID ASSET NAME').lower() in statement.text.lower()

            asset_list = self.state.get('asset-list', {})
            selected_assets = list(
                filter(
                    asset_was_mentioned,
                    asset_list.get('assets', [{}])
                )
            )

            if len(selected_assets) == 1:
                selected_asset = selected_assets[0]
                response_text = 'Ok, the asset {} was selected'.format(
                    selected_asset.get('name')
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

        return response
