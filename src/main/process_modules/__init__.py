# -*- coding: utf-8
from . import (
    las_replayer,
    flowrate_monitor,
    flowrate_linearity_monitor,
    pretest_monitor,
    sampling_monitor,
    chatbot,
)

__all__ = ['PROCESS_HANDLERS']

PROCESS_HANDLERS = {
    'las_file': las_replayer.start,
    'flowrate_monitor': flowrate_monitor.start,
    'flowrate_linearity_monitor': flowrate_linearity_monitor.start,
    'pretest_monitor': pretest_monitor.start,
    'sampling_monitor': sampling_monitor.start,
    'chatterbot': chatbot.start,
}
