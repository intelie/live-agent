# -*- coding: utf-8 -*-
from functools import partial

from chatterbot.conversation import Statement  # NOQA
from eliot import start_action

from live_agent.modules.chatbot.src.actions import CallbackAction
from live_agent.modules.chatbot.logic_adapters.base import (
    BaseBayesAdapter,
    NLPAdapter,
    WithAssetAdapter,
)

ITEM_PREFIX = "\n"


__all__ = ["TradesCounterAdapter"]


class TradesCounterAdapter(BaseBayesAdapter, NLPAdapter, WithAssetAdapter):
    """
    Counts the number of trades over the last X minutes
    """

    state_key = "trades-count-query"
    default_state = {}
    positive_examples = ["number of trades over", "count the trades on"]
    description = "Counts the number of trades over a number of minutes"
    usage_example = "count the number of trades over the last [number] minutes"

    def format_response(self, response_content, interval=None):
        if not response_content:
            result = f"No trades recorded over the last {interval} minutes"
        else:
            results = [f"Trades over the last {interval} minutes:"]
            for item in response_content:
                results.append(f"- *{item['pair']}*: {item['count']:.0f} trades")

            result = ITEM_PREFIX.join(results)

        return result

    def run_query(self, interval):
        value_query = "krakenfx => count() by pair at the end => @filter(count != null)"

        return super().run_query(
            value_query,
            realtime=False,
            span=f"last {interval} minutes",
            callback=partial(self.format_response, interval=interval),
        )

    def find_interval_value(self, statement):
        tagged_words = self.pos_tag(statement)

        # look for a number in the statement
        value = None
        for word, tag in tagged_words:
            if tag == "CD":  # CD: Cardinal number
                value = word
                break

        return value

    def can_process(self, statement):
        can_process = super().can_process(statement)
        words = statement.text.lower().split(" ")
        return can_process and ("minutes" in words)

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)
        if confidence > self.confidence_threshold:
            return CallbackAction(self.execute_action, confidence, statement=statement)

    def execute_action(self, statement):
        interval = self.find_interval_value(statement)

        if (interval is not None) and (int(interval) > 0):
            with start_action(action_type=self.state_key, interval=interval):
                response_text = self.run_query(interval)

        else:
            response_text = "I'm sorry, I didn't get the interval you want me to count"

        return response_text
