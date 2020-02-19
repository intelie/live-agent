# -*- coding: utf-8 -*-
from .actions import las_replayer

PROCESSES = {"las_replay": las_replayer.start}
