# -*- coding: utf-8 -*-
from chatterbot.conversation import Statement

from utils import logging

from .base_adapters import BaseBayesAdapter


__all__ = ['CurrentValueAdapter']


class CurrentValueAdapter(BaseBayesAdapter):
    """
    Returns the current value for a mnemonic
    """

    state_key = 'pipes_query'
    required_state = [
        'event_type',
        'mnemonic'
    ]
    default_state = {}
    positive_examples = [
        'what is the value',
        'hey what value does it',
        'do you know the value',
        'do you know what is the value',
    ]
    negative_examples = [
        'it is time to go to sleep',
        'what is your favorite color',
        'what the color of the sky',
        'i had a great time',
        'thyme is my favorite herb',
        'do you have time to look at my essay',
        'how do you have the time to do all this'
        'what is it'
    ]

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
