# -*- coding: utf-8 -*-
from pprint import pformat
from chatterbot.conversation import Statement  # NOQA
from jinja2 import Template

from .base_adapters import WithStateAdapter, BaseBayesAdapter
from .constants import (
    get_positive_examples, get_negative_examples,
    FEATURES,
    FEATURES_DESCRIPTION_TEMPLATE,
)

__all__ = [
    'BotFeaturesAdapter',
    'StateDebugAdapter',
]


class BotFeaturesAdapter(BaseBayesAdapter):
    """
    Lists the capabilities of the bot
    """

    state_key = 'bot-features'
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def prepare_response(self):
        template = Template(FEATURES_DESCRIPTION_TEMPLATE)
        response_text = template.render(
            bot_name=self.chatbot.name,
            features=[item for item in FEATURES.values() if 'description' in item]
        )
        return response_text

    def process(self, statement, additional_response_selection_parameters=None):
        self.confidence = self.get_confidence(statement)
        response = Statement(
            text=self.prepare_response()
        )
        response.confidence = self.confidence

        return response


class StateDebugAdapter(WithStateAdapter):
    """
    Displays the shared state
    """

    keyphrase = 'show me your inner self'
    state_key = 'state-debug'

    def process(self, statement, additional_response_selection_parameters=None):
        response = Statement(
            text=pformat(self.shared_state, depth=3)
        )
        response.confidence = 1

        return response

    def can_process(self, statement):
        return self.keyphrase in statement.text.lower()
