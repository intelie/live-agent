# -*- coding: utf-8 -*-

from .settings import get_monitor_parameters, get_global_mnemonics, get_probe_mnemonics

__all__ = ["init_data"]


def init_data(settings):
    event_type = settings.get("event_type")
    monitor_settings = settings.get("monitor", {})
    probes = monitor_settings["probes"]

    return dict(
        (
            probe_name,
            dict(
                event_type=event_type,
                **get_monitor_parameters(settings),
                **get_global_mnemonics(settings),
                **get_probe_mnemonics(settings, probe_name),
            ),
        )
        for probe_name in probes
    )
