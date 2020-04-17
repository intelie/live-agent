# -*- coding: utf-8 -*-
import importlib
from pprint import pformat

from chatterbot.conversation import Statement
from chatterbot.utils import validate_adapter_class, initialize_class
from chatterbot.logic import LogicAdapter
from chatterbot.adapters import Adapter

from jinja2 import Template

from ..src.actions import CallbackAction
from ..constants import FEATURES_DESCRIPTION_TEMPLATE
from .base import WithStateAdapter, BaseBayesAdapter

__all__ = ["BotFeaturesAdapter", "StateDebugAdapter", "AdapterReloaderAdapter"]


class BotFeaturesAdapter(BaseBayesAdapter):
    """
    Lists the capabilities of the bot
    """

    state_key = "bot-features"
    positive_examples = [
        "/help",
        "!help",
        "help me",
        "some help",
        "/commands",
        "!commands",
        "command list",
        "list commands",
        "list your features",
        "which features have",
        "which tasks can perform",
        "how can you help me",
        "how can you help us",
        "what can you do",
        "what can be done you",
        "what is your job",
        "how can you help me",
        "what are you capable",
        "which capabilities do you have",
        "which powers do you have",
        "what is your superpower",
        "which are your superpowers",
        "which superpowers do you have",
    ]

    def prepare_response(self):
        template = Template(FEATURES_DESCRIPTION_TEMPLATE)
        adapters = self.chatbot.logic_adapters
        response_text = template.render(
            bot_name=self.chatbot.name,
            features=[
                item
                for item in adapters
                if hasattr(item, "description") and hasattr(item, "usage_example")
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
        settings = kwargs.get("settings", {})
        self.logic_adapters = settings.get("logic_adapters", [])

    def process(self, statement, additional_response_selection_parameters=None):
        return CallbackAction(self.execute_action, confidence=1)

    def can_process(self, statement):
        return self.keyphrase in statement.text.lower()

    def execute_action(self):
        try:
            self._delete_all_adapters()

            # Reload the list of logic adapters
            self.chatbot.logic_adapters = [
                self._initialize_class(adapter)
                for adapter in self.logic_adapters
                if self._validate_adapter(adapter)
            ]
            response_text = "{} logic adapters reloaded".format(len(self.logic_adapters))

        except Exception as e:
            response_text = "Error reloading adapters: {} {}".format(e, type(e))

        return response_text

    def _delete_all_adapters(self):
        for adapter_instance in self.chatbot.logic_adapters:
            del adapter_instance

    def _initialize_class(self, adapter):
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

    def _validate_adapter(self, adapter):
        try:
            validate_adapter_class(adapter, LogicAdapter)
            is_valid = True
        except Adapter.InvalidAdapterTypeException:
            is_valid = False

        return is_valid
