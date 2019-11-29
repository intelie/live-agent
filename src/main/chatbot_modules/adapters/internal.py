# -*- coding: utf-8 -*-
import importlib
from pprint import pformat

from chatterbot.conversation import Statement  # NOQA
from chatterbot.utils import validate_adapter_class, initialize_class
from chatterbot.logic import LogicAdapter
from chatterbot.adapters import Adapter
from dda.chatbot.base import NoTextAction

from jinja2 import Template

from .base import WithStateAdapter, BaseBayesAdapter
from ..constants import (
    get_positive_examples,
    get_negative_examples,
    FEATURES,
    FEATURES_DESCRIPTION_TEMPLATE,
)

__all__ = ["BotFeaturesAdapter", "StateDebugAdapter", "AdapterReloaderAdapter"]


class BotFeaturesAdapter(BaseBayesAdapter):
    """
    Lists the capabilities of the bot
    """

    state_key = "bot-features"
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def prepare_response(self):
        template = Template(FEATURES_DESCRIPTION_TEMPLATE)
        response_text = template.render(
            bot_name=self.chatbot.name,
            features=[
                item
                for item in FEATURES.values()
                if item.get("enabled") and ("description" in item and "usage_example" in item)
            ],
        )
        return response_text

    def process(self, statement, additional_response_selection_parameters=None):
        self.confidence = self.get_confidence(statement)
        response = Statement(text=self.prepare_response())
        response.confidence = self.confidence

        return response


class StateDebugAdapter(WithStateAdapter):
    """
    Displays the shared state
    """

    keyphrase = "show me your inner self"
    state_key = "state-debug"

    def process(self, statement, additional_response_selection_parameters=None):
        response = Statement(text=pformat(self.shared_state, depth=3))
        response.confidence = 1

        return response

    def can_process(self, statement):
        return self.keyphrase in statement.text.lower()


class AdapterReloaderAdapter(WithStateAdapter):
    """
    Reloads the code for all the logic adapters
    """

    keyphrase = "reinvent yourself"
    state_key = "adapter-reloader"

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

    def process(self, statement, additional_response_selection_parameters=None):
        return ReloadAdaptersAction(confidence = 1)

    def can_process(self, statement):
        return self.keyphrase in statement.text.lower()


class ReloadAdaptersAction(NoTextAction):

    def reload(self):
        self.delete_all_adapters()

        # Reload the list of logic adapters
        constants = importlib.import_module("chatbot_modules.constants")
        constants = importlib.reload(constants)

        self.chatbot.logic_adapters = [
            self.initialize_class(adapter)
            for adapter in constants.LOGIC_ADAPTERS
            if self.validate_adapter(adapter)
        ]

    def delete_all_adapters(self):
        for adapter_instance in self.chatbot.logic_adapters:
            del adapter_instance

    def validate_adapter(self, adapter):
        try:
            validate_adapter_class(adapter, LogicAdapter)
            is_valid = True
        except Adapter.InvalidAdapterTypeException:
            is_valid = False

        return is_valid

    def initialize_class(self, adapter):
        if isinstance(adapter, dict):
            adapter.pop("logic_adapters", None)
            adapter_path = adapter.get("import_path")
        else:
            adapter_path = adapter

        # Reload the logic adapters
        module_parts = adapter_path.split(".")
        module_path = ".".join(module_parts[:-1])
        module = importlib.import_module(module_path)
        module = importlib.reload(module)

        return initialize_class(adapter, self.chatbot, **self.chatbot.context)

    def run(self):
        try:
            self.reload()
            response_text = "{} logic adapters reloaded".format(len(self.chatbot.logic_adapters))
        except Exception as e:
            response_text = "Error reloading adapters: {} {}".format(e, type(e))
        return response_text
