# -*- coding: utf-8 -*-
from .datasources import krakenfx

PROCESSES = {"krakenfx": krakenfx.start}
REQUIREMENTS = {}
