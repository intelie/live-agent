# -*- coding: utf-8 -*-
from functools import partial

from chatterbot.conversation import Statement  # NOQA

from live_client.assets import list_assets, fetch_asset_settings
from live_client.assets.utils import only_enabled_curves
from live_client.utils import logging

from chatbot.actions import CallbackAction, ShowTextAction
from chatbot.logic_adapters.base import BaseBayesAdapter, WithStateAdapter

from ..constants import ITEM_PREFIX, SELECTED_ASSET_VARIABLE_NAME


__all__ = ["AssetListAdapter", "AssetSelectionAdapter"]


class AssetListAdapter(BaseBayesAdapter, WithStateAdapter):
    """
    Interacts with the user to associate the chatbot to an asset
    """

    state_key = "asset-list"
    default_state = {}
    positive_examples = [
        "which assets exist",
        "list the assets",
        "list which assets exist",
        "show the assets",
        "show the assets list",
        "show which assets exist",
        "display the assets",
        "display the assets list",
        "display which assets exist",
    ]
    description = "List the assets available"
    usage_example = "show me the list of assets"

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        available_assets = list_assets(
            kwargs["process_name"], kwargs["process_settings"], kwargs["output_info"]
        )

        if not available_assets:
            process_name = kwargs["process_name"]
            logging.warn(f"{process_name}: No assets available. Check permissions for this user!")

        self.load_state()
        self.state = {
            "assets": available_assets,
            "asset_names": [item.get("name") for item in available_assets if "name" in item],
        }
        self.share_state()

    def process(self, statement, additional_response_selection_parameters=None):
        self.confidence = self.get_confidence(statement)

        if self.confidence > self.confidence_threshold:
            response = Statement(
                text="The known assets are:{}{}".format(
                    ITEM_PREFIX, ITEM_PREFIX.join(self.state.get("asset_names", []))
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

    state_key = SELECTED_ASSET_VARIABLE_NAME
    required_state = ["asset_id", "asset_type", "asset_name", "asset_config"]
    default_state = {}
    positive_examples = [
        "activate asset",
        "select asset",
        "set active asset",
        "update asset",
        "new asset is",
        "update asset to",
        "change asset to",
    ]
    description = "Select an asset for this room"
    usage_example = "activate the asset {asset name}"

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        process_name = kwargs["process_name"]
        process_settings = kwargs["process_settings"]
        output_info = kwargs["output_info"]

        self.asset_fetcher = partial(
            fetch_asset_settings, process_name, process_settings, output_info
        )

    def was_asset_mentioned(self, asset, statement):
        return asset.get("name", "INVALID ASSET NAME").lower() in statement.text.lower()

    def extract_asset_names(self, statement):
        asset_list = self.shared_state.get("asset-list", {})
        assets = list(
            filter(
                lambda asset: self.was_asset_mentioned(asset, statement),
                asset_list.get("assets", [{}]),
            )
        )
        return assets

    def process(self, statement, additional_response_selection_parameters=None):
        self.load_state()
        self.confidence = self.get_confidence(statement)

        response = None
        if self.confidence > self.confidence_threshold:
            selected_assets = self.extract_asset_names(statement)
            num_selected_assets = len(selected_assets)

            if num_selected_assets == 0:
                self.confidence_threshold *= 0.7
                response = ShowTextAction(
                    "I didn't get the asset name. Can you repeat please?", self.confidence
                )

            elif num_selected_assets == 1:
                response = CallbackAction(
                    self.execute_action, self.confidence, asset_info=selected_assets[0]
                )

            elif num_selected_assets > 1:
                response = ShowTextAction(
                    "I didn't understand, which of the assets you meant?{}{}".format(
                        ITEM_PREFIX, ITEM_PREFIX.join(item.get("name") for item in selected_assets)
                    ),
                    self.confidence,
                )
        return response

    def execute_action(self, asset_info):
        asset_name = asset_info.get("name")
        asset_id = asset_info.get("id", 0)
        asset_type = asset_info.get("asset_type", "rig")
        asset_config = self.asset_fetcher(asset_id, asset_type=asset_type)

        if asset_config is None:
            return f"Error fetching information about {asset_name}"

        self.state = {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "asset_name": asset_name,
            "asset_config": asset_config,
        }
        self.share_state()

        event_type = asset_config.get("event_type", None)
        asset_curves = only_enabled_curves(asset_config.get("curves", {}))

        text_templ = (
            "Ok, the asset {} was selected." '\nIt uses the event_type "{}" and has {} curves'
        )
        return text_templ.format(asset_name, event_type, len(asset_curves.keys()))
