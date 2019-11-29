import json
import traceback

from importlib import import_module


def is_action_response(response):
    return response.text.startswith("::")


def get_action_handler(response):
    module_name, handler_name, params = parse_action_response(response)
    module = import_module(module_name)
    try:
        handler = getattr(module, handler_name)
    except Exception:
        traceback.print_exc()
        raise

    return handler, params


def parse_action_response(response):
    lines = response.text.split("\n")
    parts = lines[0][2:].split(".")
    module_name = ".".join(parts[:-1])
    handler_name = parts[-1]

    params = json.loads(lines[1])
    return (module_name, handler_name, params)


def build_action_response(handler, params=None):
    fn_fully_qualified_name = f"{handler.__module__}.{handler.__name__}"
    fn_params = json.dumps(params or {})
    return f"::{fn_fully_qualified_name}\n{fn_params}"
