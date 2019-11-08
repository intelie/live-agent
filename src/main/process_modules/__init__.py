# -*- coding: utf-8
from . import (
    alert_reference_monitor,
    chatbot,
    flowrate_monitor,
    flowrate_linearity_monitor,
    las_replayer,
    pretest_monitor,
    sampling_monitor,
)

__all__ = ["PROCESS_HANDLERS"]

PROCESS_HANDLERS = {
    "alert_reference_monitor": alert_reference_monitor.start,
    "chatterbot": chatbot.start,
    "flowrate_monitor": flowrate_monitor.start,
    "flowrate_linearity_monitor": flowrate_linearity_monitor.start,
    "las_file": las_replayer.start,
    "pretest_monitor": pretest_monitor.start,
    "sampling_monitor": sampling_monitor.start,
}
