# -*- coding: utf-8 -*-
from utils.monitors import get_monitor_parameters, get_global_mnemonics

__all__ = ["init_probes_data"]


def get_probe_mnemonics(settings, probe_name):
    monitor_settings = settings.get("monitor", {})
    mnemonics = monitor_settings["mnemonics"]
    probe_prefix = f"probe{probe_name}"

    filtered_mnemonics = dict(
        (label.replace(probe_prefix, "").strip(), mnemonic)
        for label, mnemonic in mnemonics.items()
        if label.startswith(probe_prefix)
    )
    probe_mnemonics = dict(
        (label.replace(" ", "_"), mnemonic) for label, mnemonic in filtered_mnemonics.items()
    )
    return probe_mnemonics


def init_probes_data(settings):
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
