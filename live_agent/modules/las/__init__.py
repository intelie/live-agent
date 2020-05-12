# -*- coding: utf-8 -*-
from .datasources import las_replayer

PROCESSES = {"las_replay": las_replayer.start}
