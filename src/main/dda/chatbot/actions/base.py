class Action:
    """ An action to be executed after the assistent selected a response.

    The action can provide a field "message" which the default run implemention
    will return.
    If no Action.message is provided a run method must be defined in the subclass.
    """

    def __init__(self, chatbot = None, liveclient = None):
        self.chatbot = chatbot
        self.liveclient = liveclient

    def run(self, params):
        return self.message
