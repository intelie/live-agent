# -*- coding: utf-8 -*-
from functools import partial
import time
import json
from uuid import uuid4

from chatterbot.conversation import Statement  # NOQA
from eliot import start_action

from live_client.events import annotation
from live_client.assets import list_assets, fetch_asset_settings
from live_client.assets import run_analysis
from live_client.assets.curves import only_enabled_curves
from live_client.utils import logging
from live_client.utils.timestamp import get_timestamp
from live_client.events.constants import UOM_KEY, VALUE_KEY, TIMESTAMP_KEY

from live_agent.modules.chatbot.src.actions import CallbackAction, ShowTextAction
from live_agent.modules.chatbot.logic_adapters.base import (
    BaseBayesAdapter,
    NLPAdapter,
    WithAssetAdapter,
    WithStateAdapter,
)

from ..constants import ITEM_PREFIX, SELECTED_ASSET_VARIABLE_NAME


__all__ = ["AssetListAdapter", "AssetSelectionAdapter", "AutoAnalysisAdapter"]


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

        available_assets = list_assets(kwargs["settings"])

        if not available_assets:
            logging.warn(f"No assets available. Check permissions for this user!")

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

        settings = kwargs["settings"]

        self.asset_fetcher = partial(fetch_asset_settings, settings)

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


class AutoAnalysisAdapter(BaseBayesAdapter, NLPAdapter, WithAssetAdapter):
    """
    Analyze a curve on live
    """

    state_key = "auto-analysis"
    required_state = ["assetId", "channel", "begin", "end", "computeFields"]
    default_state = {"computeFields": ["min", "max", "avg", "stdev", "linreg", "derivatives"]}
    positive_examples = [
        "analyse",
        "analyse mnemonic",
        "analyse curve",
        "analyse mnemonic",
        "analyse curve",
        "run an analysis on",
        "execute an analysis on",
        "can you analyse mnemonic",
        "can you analyse curve",
        "can you run an analysis on",
        "can you execute an analysis on",
    ]
    description = "Run an analysis on a curve"
    usage_example = "run an analysis on {curve name}"

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)
        settings = kwargs.get("settings", {})
        self.annotator = partial(annotation.create, settings=settings)

        self.room_id = kwargs["room_id"]
        self.analyzer = partial(run_analysis, settings)

    def run_analysis(self, asset, curve, begin=None, duration=30000):
        if begin is None:
            begin = get_timestamp() - duration

        end = begin + duration

        analysis_results = self.analyzer(
            assetId="{0[asset_type]}/{0[asset_id]}".format(asset),
            channel=curve,
            qualifier=curve,
            computeFields=self.default_state.get("computeFields"),
            begin=begin,
            end=end,
        )

        if analysis_results:
            # Gerar annotation
            analysis_results.update(
                __src="auto-analysis", uid=str(uuid4()), createdAt=get_timestamp()
            )
            with start_action(action_type="create annotation", curve=curve):
                self.annotator(analysis_results, room={"id": self.room_id})

            response_text = "Analysis of curve {} finished".format(curve)

        else:
            response_text = "Analysis of curve {} returned no data".format(curve)

        return response_text

    def process_analysis(self, statement, selected_asset, begin=None):
        selected_curves = self.find_selected_curves(statement)
        num_selected_curves = len(selected_curves)

        if num_selected_curves == 1:
            selected_curve = selected_curves[0]

            ##
            # Iniciar analise
            with start_action(action_type=self.state_key, curve=selected_curve):
                response_text = self.run_analysis(selected_asset, selected_curve)

        elif num_selected_curves == 0:
            response_text = "I didn't get the curve name. Can you repeat please?"

        else:
            response_text = "I'm sorry, which of the curves you want to analyse?{}{}".format(
                ITEM_PREFIX, ITEM_PREFIX.join(selected_curves)
            )

        return response_text

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)

        if confidence > self.confidence_threshold:
            self.load_state()
            selected_asset = self.get_selected_asset()
            if selected_asset == {}:
                response_text = "No asset selected. Please select an asset first."
            else:
                return CallbackAction(
                    self.execute_action,
                    confidence,
                    statement=statement,
                    selected_asset=selected_asset,
                )

            response = Statement(text=response_text)
            response.confidence = confidence
        else:
            response = None

        return response

    def execute_action(self, statement, selected_asset):
        return self.process_analysis(statement, selected_asset)


class CurrentValueQueryAdapter(BaseBayesAdapter, NLPAdapter, WithAssetAdapter):
    """
    Returns the current value for a mnemonic
    """

    state_key = "current-query"
    default_state = {}
    positive_examples = ["current value", "value now"]
    description = "Query the most recent value for a curve"
    usage_example = "what is the current value for {curve name}?"

    def format_response(self, response_content, target_curve=None):
        if not response_content:
            result = "No information about {target_curve}".format(target_curve=target_curve)
        else:
            results = []
            for item in response_content:
                query_result = json.loads(item.get(target_curve, "{}"))
                timestamp = int(item.get(TIMESTAMP_KEY, 0)) or None

                try:
                    value = query_result.get(VALUE_KEY)
                    uom = query_result.get(UOM_KEY)

                    if uom:
                        query_result = "{0:.2f} {1}".format(value, uom)
                    else:
                        query_result = "{0:.2f}".format(value)

                except Exception as e:
                    logging.error("{}: {} ({})".format(self.__class__.__name__, e, type(e)))

                if timestamp:
                    time_diff = time.time() - (timestamp / 1000)

                if timestamp < 2:
                    response_age = f"{time_diff:.1f} second ago"
                else:
                    response_age = f"{time_diff:.1f} seconds ago"

                results.append(f"{target_curve} was *{query_result}* {response_age}.")

            result = ITEM_PREFIX.join(results)

        return result

    def run_query(self, target_curve):
        selected_asset = self.get_selected_asset()
        if selected_asset:
            asset_config = selected_asset.get("asset_config", {})

            value_query = """
            {event_type} .flags:nocount .flags:reversed
            => @filter({{{target_curve}}} != null)
            => {{{target_curve}}}:map():json() as {{{target_curve}}}
            """.format(
                event_type=asset_config["filter"], target_curve=target_curve
            )

            return super().run_query(
                value_query,
                realtime=False,
                span="since ts 0 #partial='1'",
                callback=partial(self.format_response, target_curve=target_curve),
            )

    def can_process(self, statement):
        can_process = super().can_process(statement)
        words = statement.text.lower().split(" ")
        return can_process and ("now" in words or "current" in words)

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)
        if confidence > self.confidence_threshold:
            self.load_state()
            selected_asset = self.get_selected_asset()

            if selected_asset == {}:
                return ShowTextAction(
                    "No asset selected. Please select an asset first.", confidence
                )
            else:
                return CallbackAction(
                    self.execute_action,
                    confidence,
                    statement=statement,
                    selected_asset=selected_asset,
                )

    def execute_action(self, statement, selected_asset):
        selected_curves = self.find_selected_curves(statement)
        num_selected_curves = len(selected_curves)

        if num_selected_curves == 0:
            response_text = "I didn't get the curve name. Can you repeat please?"

        elif num_selected_curves == 1:
            selected_curve = selected_curves[0]

            with start_action(action_type=self.state_key, curve=selected_curve):
                response_text = self.run_query(selected_curve)

        else:
            response_text = "I'm sorry, which of the curves you meant?{}{}".format(
                ITEM_PREFIX, ITEM_PREFIX.join(selected_curves)
            )

        return response_text
