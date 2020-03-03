# -*- coding: utf-8 -*-

__all__ = ["get_global_mnemonics", "get_probe_mnemonics", "get_monitor_parameters"]


def get_global_mnemonics(monitor_settings):
    mnemonics = monitor_settings["mnemonics"]
    probe_prefix = "probe"

    filtered_mnemonics = dict(
        (f"{label} mnemonic", mnemonic)
        for label, mnemonic in mnemonics.items()
        if not label.startswith(probe_prefix)
    )
    global_mnemonics = dict(
        (label.replace(" ", "_"), mnemonic) for label, mnemonic in filtered_mnemonics.items()
    )
    return global_mnemonics


def get_probe_mnemonics(monitor_settings, probe_name):
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


def get_monitor_parameters(monitor_settings, ignored_keys=None):
    if not ignored_keys:
        ignored_keys = ["probes", "mnemonics"]

    return dict((key, value) for key, value in monitor_settings.items() if key not in ignored_keys)
