# -*- coding: utf-8 -*-
import csv
from setproctitle import setproctitle

import lasio

from live_client.utils import logging

__all__ = ["start"]


def open_files(settings, iterations):
    path_list = settings["path_list"]
    index_mnemonic = settings["index_mnemonic"]

    path_index = iterations

    try:
        las_path, chat_path = path_list[path_index]
        with open(las_path, "r") as las_file:
            data = lasio.read(las_file)

        if chat_path:
            with open(chat_path, "r") as chat_file:
                chat_data = list(csv.DictReader(chat_file))

            logging.debug("Success opening files {} and {}>".format(las_path, chat_path))
        else:
            chat_data = []
            logging.debug("Success opening file {}>".format(las_path))

        success = True
    except Exception as e:
        data = e
        chat_data = None
        success = False
        logging.error("Error opening file {}, {}<{}>".format(las_path, e, type(e)))

    return success, data, chat_data, index_mnemonic


def export_curves_data(event_type, las_data, chat_data, index_mnemonic, settings):
    logging.info("Exporting curves for {}".format(event_type))
    output_dir = settings.get("temp_dir", "/tmp")

    source_name = las_data.version.SOURCE.value
    output_filename = "{}/{}.csv".format(output_dir, source_name)

    with open(output_filename, "w") as output_file:
        writer = csv.writer(output_file)

        for curve in las_data.curves:
            writer.writerow(
                ["{} - {}".format(curve.mnemonic, curve.descr), curve.mnemonic, curve.unit, "", ""]
            )

    logging.info("File {} created".format(output_filename))


def start(settings, **kwargs):
    event_type = settings["output"]["event_type"]
    setproctitle('DDA: LAS replayer for "{}"'.format(event_type))

    handling_func = export_curves_data

    iterations = 0
    while True:
        try:
            success, las_data, chat_data, index_mnemonic = open_files(settings, iterations)

            if success:
                handling_func(event_type, las_data, chat_data, index_mnemonic, settings)
                logging.info("{}: Iteration {} successful".format(event_type, iterations))

            else:
                logging.info("{}: Single pass mode, exiting".format(event_type))
                break

        except Exception as e:
            logging.error("{}: Error processing events, {}<{}>".format(event_type, e, type(e)))

        iterations += 1

    return
