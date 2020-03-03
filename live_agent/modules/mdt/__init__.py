# -*- coding: utf-8 -*-
from .monitors import (
    flowrate_linearity_monitor,
    flowrate_monitor,
    pretest_monitor,
    sampling_monitor,
)

PROCESSES = {
    "flowrate_monitor": flowrate_monitor.start,
    "flowrate_linearity_monitor": flowrate_linearity_monitor.start,
    "pretest_monitor": pretest_monitor.start,
    "sampling_monitor": sampling_monitor.start,
}
