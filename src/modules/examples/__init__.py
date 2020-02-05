# -*- coding: utf-8 -*-
from .monitors import alert_reference_monitor

PROCESSES = {"alert_reference_monitor": alert_reference_monitor.start}
