from chatterbot.conversation import Statement


class ActionStatement(Statement):
    def __init__(self, text, confidence=None, in_response_to=None, **kwargs):
        super().__init__(text, in_response_to, **kwargs)
        self.confidence = confidence
        self.chatbot = kwargs.get("chatbot")
        self.liveclient = kwargs.get("liveclient")

    def run(self):
        raise NotImplementedError()


class ShowTextAction(ActionStatement):
    def run(self):
        return self.text


class NoTextAction(ActionStatement):
    def __init__(self, confidence=None, in_response_to=None, **kwargs):
        super().__init__("", confidence, in_response_to, **kwargs)
        self.params = kwargs


class CallbackAction(ActionStatement):
    def __init__(self, callback, confidence=None, in_response_to=None, **kwargs):
        super().__init__("", confidence, in_response_to, **kwargs)
        self.params = kwargs
        self.callback = callback

    def run(self):
        return self.callback(**self.params)
