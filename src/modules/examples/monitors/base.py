# -*- coding: utf-8 -*-

__all__ = ["Monitor"]


class Monitor:
    """Base class to implement monitors"""

    monitor_name = "base_monitor"

    def __init__(self, settings, **kwargs):
        self.settings = settings
        self.kwargs = kwargs

    def run(self):
        raise NotImplementedError("Monitors must define a start method")

    @classmethod
    def start(cls, settings, **kwargs):
        monitor = cls(settings, **kwargs)
        monitor.run()
