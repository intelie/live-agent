import json

from chatterbot.conversation import Statement

from ..actions.utils import build_action_response


def build_statement(text, confidence):
    statement = Statement(text)
    statement.confidence = confidence
    return statement


def build_action_statement(confidence, handler, params=None):
    return build_statement(build_action_response(handler, params), confidence)
