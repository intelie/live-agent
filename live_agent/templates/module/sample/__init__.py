# -*- coding: utf-8 -*-
from .datasources import krakenfx
from .monitors import trade_frequency

PROCESSES = {"krakenfx": krakenfx.start, "trade_frequency": trade_frequency.start}
REQUIREMENTS = {}
