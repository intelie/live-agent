# -*- coding: utf-8 -*-
import json

from utils import las_parser
from utils import raw_over_tcp

__all__ = []


def resolve_input_handler(settings):
    input_handlers = {
        'las_file': las_parser.events_from_las,
    }
    input_settings = settings.get('input', {})
    input_type = input_settings.get('type', 'image')
    return input_handlers.get(input_type)


def resolve_output_handler(settings):
    output_handlers = {
        'raw_over_tcp': raw_over_tcp.format_and_send,
    }
    output_settings = settings.get('output', {})
    output_type = output_settings.get('type', 'csv_over_tcp')
    return output_handlers.get(output_type)


def process_inputs(settings):
    input_func = resolve_input_handler(settings)
    output_func = resolve_output_handler(settings)

    return input_func(output_func, settings)


if __name__ == '__main__':

    with open('settings.json', 'r') as fd:
        settings = json.load(fd)
        process_inputs(settings)
