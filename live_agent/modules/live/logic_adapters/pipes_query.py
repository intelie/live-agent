# -*- coding: utf-8 -*-
from functools import partial
import time
import json

from eliot import start_action

from live_client.events.constants import UOM_KEY, VALUE_KEY, TIMESTAMP_KEY
from live_client.utils import logging

from live_agent.modules.chatbot.src.actions import CallbackAction, ShowTextAction
from live_agent.modules.chatbot.logic_adapters.base import (
    BaseBayesAdapter,
    NLPAdapter,
    WithAssetAdapter,
)
from ..constants import ITEM_PREFIX


__all__ = ["CurrentValueQueryAdapter", "EtimQueryAdapter"]


class CurrentValueQueryAdapter(BaseBayesAdapter, NLPAdapter, WithAssetAdapter):
    """
    Returns the current value for a mnemonic
    """

    state_key = "current-query"
    default_state = {}
    positive_examples = ["current value", "value now"]
    description = "Query the most recent value for a curve"
    usage_example = "what is the current value for {curve name}?"

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

    def process_query(self, statement, selected_asset):
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
                    self.process_query,
                    confidence,
                    statement=statement,
                    selected_asset=selected_asset,
                )

    def can_process(self, statement):
        words = statement.text.lower().split(" ")
        return ("value" in words) and ("now" in words or "current" in words)


class EtimQueryAdapter(BaseBayesAdapter, NLPAdapter, WithAssetAdapter):
    """
    Returns the value for a mnemonic at an specific ETIM
    """

    state_key = "etim-query"
    index_curve = "ETIM"
    default_state = {}
    positive_examples = ["value at ETIM", "what value for when ETIM"]
    description = "Query the value for a curve at an specific ETIM value"
    usage_example = "what is the value for {curve name} at ETIM 1500?"

    def find_index_value(self, statement):
        tagged_words = self.pos_tag(statement)

        # Find out where the {index_curve} was mentioned
        # and look for a number after the mention
        value = None
        index_mentioned = False
        for word, tag in tagged_words:
            if word == self.index_curve:
                index_mentioned = True

            if index_mentioned and (tag == "CD"):  # CD: Cardinal number
                value = word
                break

        return value

    def run_query(self, target_curve, index_value):
        selected_asset = self.get_selected_asset()
        if selected_asset:
            asset_config = selected_asset.get("asset_config", {})

            value_query = """
            {event_type} .flags:nocount .flags:reversed
            => {{{target_curve}}}:map():json() as {{{target_curve}}},
               {{{index_curve}}}->value as {{{index_curve}}}
            => @filter({{{index_curve}}}#:round() == {index_value})
            """.format(
                event_type=asset_config["filter"],
                target_curve=target_curve,
                index_curve=self.index_curve,
                index_value=index_value,
            )

            return super().run_query(
                value_query,
                realtime=False,
                span="since ts 0 #partial='1'",
                callback=partial(
                    self.format_response, target_curve=target_curve, index_value=index_value
                ),
            )

    def format_response(self, response_content, target_curve=None, index_value=None):
        if not response_content:
            result = "No information about {target_curve} at {index_curve} {index_value}".format(
                target_curve=target_curve, index_curve=self.index_curve, index_value=index_value
            )
        else:
            results = []
            for item in response_content:
                index_value = float(item.get(self.index_curve, 0))
                query_result = json.loads(item.get(target_curve, "{}"))

                try:
                    value = query_result.get(VALUE_KEY)
                    uom = query_result.get(UOM_KEY)

                    if uom:
                        query_result = "{0:.2f} {1}".format(value, uom)
                    else:
                        query_result = "{0:.2f}".format(value)

                except Exception as e:
                    logging.error("{}: {} ({})".format(self.__class__.__name__, e, type(e)))

                results.append(
                    f"{target_curve} was *{query_result}* at {self.index_curve} {index_value:.0f}."
                )

            result = ITEM_PREFIX.join(results)

        return result

    def process_indexed_query(self, statement, selected_asset):
        selected_curves = self.find_selected_curves(statement)
        num_selected_curves = len(selected_curves)
        selected_value = self.find_index_value(statement)

        if selected_value is None:
            response_text = "I didn't get which ETIM value you want me to use as reference."

        elif num_selected_curves == 0:
            response_text = "I didn't get the curve name. Can you repeat please?"

        elif num_selected_curves == 1:
            selected_curve = selected_curves[0]

            with start_action(action_type=self.state_key, curve=selected_curve):
                response_text = self.run_query(selected_curve, selected_value)

        else:
            response_text = "I'm sorry, which of the curves you meant?{}{}".format(
                ITEM_PREFIX, ITEM_PREFIX.join(selected_curves)
            )

        return response_text

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)
        response = None

        if confidence > self.confidence_threshold:
            self.load_state()
            selected_asset = self.get_selected_asset()
            if selected_asset == {}:
                response = ShowTextAction(
                    "No asset selected. Please select an asset first.", confidence
                )
            else:
                response = CallbackAction(
                    self.process_indexed_query,
                    confidence,
                    statement=statement,
                    selected_asset=selected_asset,
                )

        return response

    def can_process(self, statement):
        return "ETIM" in statement.text.upper().split(" ")