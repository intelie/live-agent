# -*- coding: utf-8
from . import las_parser

__all__ = ['PROCESS_HANDLERS']

PROCESS_HANDLERS = {
    'las_file': las_parser.events_from_las,
}
