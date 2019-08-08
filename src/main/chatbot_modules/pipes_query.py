# -*- coding: utf-8 -*-
from chatterbot.conversation import Statement

from utils import logging

from .base_adapters import BaseBayesAdapter
from .constants import get_positive_examples, get_negative_examples


__all__ = ['CurrentValueAdapter']


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

        state = additional_response_selection_parameters.get(
            self.state_key, self.default_state
        )

        response = Statement(text="query: {}, confidence={}".format(statement.search_text, confidence))

        response.confidence = confidence
        response.state = state
        return response
