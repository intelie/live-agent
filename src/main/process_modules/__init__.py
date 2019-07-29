# -*- coding: utf-8
from . import (
    las_replayer,
    flowrate_monitor,
    pretest_monitor,
    sampling_monitor,
    chatbot,
    las_feature_selector,
    streaming_feature_selector,
)

__all__ = ['PROCESS_HANDLERS']

PROCESS_HANDLERS = {
    'las_file': las_replayer.start,
    'flowrate_monitor': flowrate_monitor.start,
    'pretest_monitor': pretest_monitor.start,
    'sampling_monitor': sampling_monitor.start,
    'chatterbot': chatbot.start,
    'las_feature_selection': las_feature_selector.start,
    'streaming_feature_selection': streaming_feature_selector.start,
}
