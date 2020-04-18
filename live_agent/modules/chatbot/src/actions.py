from chatterbot.conversation import Statement


class ActionStatement(Statement):
    def __init__(self, text, confidence=None, in_response_to=None, **kwargs):
        super().__init__(text, in_response_to, **kwargs)
        self.confidence = confidence
        self._chatbot = kwargs.get("chatbot")

    def run(self):
        raise NotImplementedError()

    def _instance_text(self):
        return f"{self.__class__.__name__}: {id(self)}"

    @property
    def chatbot(self):
        return self._chatbot

    @chatbot.setter
    def chatbot(self, value):
        self.set_chatbot(value)

    def set_chatbot(self, value):
        self._chatbot = value
        return self

    @property
    def live_client(self):
        return self._chatbot.live_client


class ShowTextAction(ActionStatement):
    def run(self):
        return self.text


class NoTextAction(ActionStatement):
    def __init__(self, confidence=None, in_response_to=None, **kwargs):
        super().__init__(self._instance_text(), confidence, in_response_to, **kwargs)
        self.params = kwargs


class CallbackAction(ActionStatement):
    def __init__(self, callback, confidence=None, in_response_to=None, **kwargs):
        super().__init__(self._instance_text(), confidence, in_response_to, **kwargs)
        self.params = kwargs
        self.callback = callback

    def run(self):
        return self.callback(**self.params)


class ChainedAction(ActionStatement):
    def __init__(self, actions, confidence=None, in_response_to=None, **kwargs):
        super().__init__(self._instance_text(), confidence, in_response_to, **kwargs)
        self.actions = actions

    def run(self):
        for action in self.actions:
            try:
                action.run()
            except Exception as e:
                return str(e)
