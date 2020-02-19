# -*- coding: utf-8 -*-
import importlib
import sys
from pathlib import PurePath

from live_client.utils import logging

__all__ = ["load_enabled_modules"]


def update_pythonpath():
    self_path = PurePath(__file__)
    parent_path = self_path.parent
    modules_path = PurePath(parent_path, "../../modules")
    sys.path.append(str(modules_path))


def log_and_import(name, package=None):
    try:
        return importlib.import_module(name)
    except Exception as e:
        logging.info(f"Error importing {name} (from package={package}): {e}")


def load_enabled_modules(settings):
    update_pythonpath()
    modules = []
    for name in settings.get("enabled_modules", []):
        module = log_and_import(name)
        if module is not None:
            modules.append(module)

    return modules


def load_process_handlers(settings):
    enabled_modules = load_enabled_modules(settings)
    process_handlers = {}
    for module in enabled_modules:
        process_handlers.update(**module.PROCESSES)

    return process_handlers
