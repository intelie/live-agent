# -*- coding: utf-8 -*-
from functools import partial
from chatterbot.conversation import Statement
from eliot import start_action

from .base_adapters import BaseBayesAdapter, NLPAdapter, WithAssetAdapter
from .constants import get_positive_examples, get_negative_examples


__all__ = [
    'EtimQueryAdapter',
]

ITEM_PREFIX = '\n  '


class EtimQueryAdapter(BaseBayesAdapter, NLPAdapter, WithAssetAdapter):
    """
    Returns the current value for a mnemonic
    """

    state_key = 'etim-query'
    index_curve = 'ETIM'
    default_state = {}
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def find_index_value(self, statement):
        tagged_words = self.pos_tag(statement)

        # Find out where the {index_curve} was mentioned
        # and look for a number after the mention
        value = None
        index_mentioned = False
        for word, tag in tagged_words:
            if word == self.index_curve:
                index_mentioned = True

            if index_mentioned and (tag == 'CD'):  # CD: Cardinal number
                value = word
                break

        return value

    def run_query(self, target_curve, target_value):
        selected_asset = self.get_selected_asset()
        if selected_asset:
            asset_config = selected_asset.get('asset_config', {})

            value_query = '''{event_type} .flags:nocount
                => {target_curve}, {index_curve}->value as {index_curve}
                => @filter({index_curve}#:round() == {target_value})
            '''.format(
                event_type=asset_config['filter'],
                target_curve=target_curve,
                index_curve=self.index_curve,
                target_value=target_value,
            )

            return super().run_query(
                value_query,
                realtime=False,
                span="since ts 0 #partial='1'",
                callback=partial(
                    self.format_response,
                    target_curve=target_curve,
                    target_value=target_value
                )
            )

    def format_response(self, response_content, target_curve=None, target_value=None):
        if not response_content:
            result = 'No information about {target_curve} at {index_curve} {target_value}'.format(
                target_curve=target_curve,
                index_curve=self.index_curve,
                target_value=target_value,
            )
        else:
            results = []
            for item in response_content:
                index_value = item.get(self.index_curve)
                query_result = item.get(target_curve)

                results.append(
                    "At {index_curve} {index_value}, {target_curve} was {query_result}".format(
                        target_curve=target_curve,
                        query_result=query_result,
                        index_curve=self.index_curve,
                        index_value=index_value
                    )
                )

            result = ITEM_PREFIX.join(results)

        return result

    def can_process(self, statement):
        mentioned_curves = self.list_mentioned_curves(statement)
        return (
            (len(mentioned_curves) > 1) and
            self.index_curve in mentioned_curves and
            super().can_process(statement)
        )

    def process(self, statement, additional_response_selection_parameters=None):
        self.confidence = self.get_confidence(statement)
        response = None

        if self.confidence > self.confidence_threshold:
            self.load_state()
            selected_asset = self.get_selected_asset()

            if selected_asset is None:
                response_text = "No asset selected. Please select an asset first."
            else:
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
                        self.confidence = 1

                else:
                    response_text = "I'm sorry, which of the curves you chose?{}{}".format(
                        ITEM_PREFIX,
                        ITEM_PREFIX.join(selected_curves)
                    )

            response = Statement(text=response_text)
            response.confidence = self.confidence

        return response
