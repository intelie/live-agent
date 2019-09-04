# -*- coding: utf-8 -*-
import nltk

from chatterbot.conversation import Statement

from utils import logging

from .base_adapters import BaseBayesAdapter, WithAssetAdapter
from .constants import get_positive_examples, get_negative_examples


__all__ = [
    'CurrentValueAdapter',
    'EtimQueryAdapter',
]

ITEM_PREFIX = '\n  '


class CurrentValueAdapter(BaseBayesAdapter):
    """
    Returns the current value for a mnemonic
    """

    state_key = 'pipes-current-value'
    required_state = [
        'event_type',
        'mnemonic'
    ]
    default_state = {}
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def process(self, statement, additional_response_selection_parameters=None):
        logging.info('Search text for "{}": "{}"'.format(statement, statement.search_text))

        my_features = self.analyze_features(statement.text.lower())
        confidence = self.classifier.classify(my_features)

        created_at = getattr(statement, 'created_at')
        if created_at:
            user_timezone = created_at.tzinfo
            logging.info('user_timezone is {}'.format(user_timezone))

        state = additional_response_selection_parameters.get(
            self.state_key, self.default_state
        )

        response = Statement(text="query: {}, confidence={}".format(statement.search_text, confidence))

        response.confidence = confidence
        response.state = state
        return response


class EtimQueryAdapter(BaseBayesAdapter, WithAssetAdapter):
    """
    Returns the current value for a mnemonic
    """

    state_key = 'etim-query'
    index_curve = 'ETIM'
    default_state = {}
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        self.chatbot = chatbot
        self.query_runner = kwargs.get('functions', {})['run_query']

    def parse_parts_of_speech(self, statement):
        tokens = nltk.word_tokenize(statement.text)
        return nltk.pos_tag(tokens)

    def find_index_value(self, statement):
        tagged_words = self.parse_parts_of_speech(statement)
        logging.info(tagged_words)

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

            results_process, results_queue = self.query_runner(
                value_query,
                realtime=False,
                span="since ts 0 #partial='1'",
            )

            result = []
            while True:
                event = results_queue.get()
                logging.debug(event)

                event_data = event.get('data', {})
                event_type = event_data.get('type')
                if event_type == 'event':
                    result = event_data.get('content', [])
                elif event_type != 'stop':
                    continue

                return self.format_response(result, target_curve, target_value)

    def format_response(self, response_content, target_curve, target_value):
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
        logging.debug("Mentioned curves are: {}".format(', '.join(mentioned_curves)))
        return (
            self.index_curve in mentioned_curves and
            (len(mentioned_curves) > 1) and
            super().can_process(statement)
        )

    def process(self, statement, additional_response_selection_parameters=None):
        self.confidence = self.get_confidence(statement)

        if self.confidence > self.confidence_threshold:
            self.load_state()
            selected_asset = self.get_selected_asset()

            if selected_asset is None:
                response_text = "No asset selected. Please select an asset first."
            else:
                mentioned_curves = dict(
                    (name, data)
                    for name, data in self.list_mentioned_curves(statement).items()
                    if name != self.index_curve
                )

                # Try to find an exact mention to a curve
                selected_curves = [
                    name for name, match_data in mentioned_curves.items()
                    if match_data.get('exact') is True
                ]

                # Failing that, use all matches
                if not selected_curves:
                    selected_curves = list(mentioned_curves.keys())

                selected_value = self.find_index_value(statement)

                if selected_value and (len(selected_curves) == 1):
                    selected_curve = selected_curves[0]

                    self.confidence = 1
                    response_text = self.run_query(selected_curve, selected_value)

                elif len(selected_curves) > 1:
                    response_text = "I didn't understand, which of the curves you chose?{}{}".format(
                        ITEM_PREFIX,
                        ITEM_PREFIX.join(selected_curves)
                    )

                elif selected_value is None:
                    response_text = "I didn't get which ETIM value you want me to use as reference."

                else:
                    response_text = "I didn't get the curve name. Can you repeat please?"

            response = Statement(text=response_text)
            response.confidence = self.confidence
        else:
            response = None

        return response
