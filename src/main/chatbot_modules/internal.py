# -*- coding: utf-8 -*-
from pprint import pformat
from chatterbot.conversation import Statement  # NOQA

from .base_adapters import WithStateAdapter


__all__ = [
    'StateDebugAdapter',
]


class StateDebugAdapter(WithStateAdapter):
    """
    Displays the shared state
    """

    keyphrase = 'show me your inner self'
    state_key = 'state-debug'

    def process(self, statement, additional_response_selection_parameters=None):
        response = Statement(
            text=pformat(self.shared_state)
        )
        response.confidence = 1

        return response

    def can_process(self, statement):
        return self.keyphrase in statement.text.lower()
