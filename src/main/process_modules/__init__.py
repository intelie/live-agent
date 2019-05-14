# -*- coding: utf-8
from . import (
    las_parser,
    flowrate_monitor
)

__all__ = ['PROCESS_HANDLERS']

PROCESS_HANDLERS = {
    'las_file': las_parser.events_from_las,
    'flowrate_monitor': flowrate_monitor.notify_frequent_changes,
}
