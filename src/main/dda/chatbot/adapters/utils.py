import json

from chatterbot.conversation import Statement

def build_statement(text, confidence):
    statement = Statement(text)
    statement.confidence = confidence
    return statement


def build_action_statement(confidence, handler, params=None):
    return build_statement(build_action_call_str(handler, params), confidence)


def build_action_call_str(handler, params=None):
    fn_fully_qualified_name = f"{handler.__module__}.{handler.__name__}"
    fn_params = json.dumps(params or {})
    return f"::{fn_fully_qualified_name}\n{fn_params}"
