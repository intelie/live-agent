import re

from chatterbot.logic import LogicAdapter

from ..src.actions import CallbackAction, ShowTextAction


class BotVariablesAdapter(LogicAdapter):

    set_command_regex = r"set\s+(.+?)\s*=\s*(.+?)\s*$"
    get_command_regex = r"get\s+(.+?)\s*$"

    def can_process(self, statement):
        words = re.split(r"\s+", statement.text)
        return ("set" in words) or ("get" in words)

    def process(self, statement, additional_response_selection_parameters=None):
        text = statement.text
        m = re.match(self.set_command_regex, text)
        if m is not None:
            name = m.group(1)
            value = m.group(2)
            return CallbackAction(self.handle_set_variable, confidence=1, name=name, value=value)

        m = re.match(self.get_command_regex, text)
        if m is not None:
            name = m.group(1)
            return CallbackAction(self.handle_get_variable, confidence=1, name=name)

        return ShowTextAction(f"Unable to parse command: {text}", confidence=0.5)

    def handle_set_variable(self, name, value):
        self.chatbot.setvar(name, value)
        return f"`> {name} = {value}`"

    def handle_get_variable(self, name):
        value = self.chatbot.getvar(name)
        value = str(value or "Not defined")
        return f"`> {name} = {value}`"
