# -*- coding: utf-8
from . import (
    las_replayer,
    flowrate_monitor,
    pretest_monitor,
    sampling_monitor,
)

__all__ = ['PROCESS_HANDLERS']

PROCESS_HANDLERS = {
    'las_file': las_replayer.start,
    'flowrate_monitor': flowrate_monitor.start,
    'pretest_monitor': pretest_monitor.start,
    'sampling_monitor': sampling_monitor.start,
}
