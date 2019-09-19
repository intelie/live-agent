# -*- coding: utf-8 -*-
import requests
from requests.exceptions import RequestException

from eliot import start_action

from live_client.utils import logging

__all__ = [
    'make_request',
    'only_enabled_curves',
]


def build_session(process_settings):
    live_settings = process_settings['live']
    username = live_settings['username']
    password = live_settings['password']

    session = requests.Session()
    session.auth = (username, password)

    return session


def make_request(process_name, process_settings, output_info, url):
    connection_func, output_settings = output_info

    if 'session' not in output_settings:
        output_settings.update(
            session=build_session(process_settings)
        )

    session = output_settings['session']

    with start_action(action_type=u"make request", url=url):
        try:
            response = session.get(url)
            response.raise_for_status()
            result = response.json()
        except RequestException as e:
            logging.exception("ERROR: Error during request for {}, {}<{}>".format(url, e, type(e)))
            result = None

    return result


def only_enabled_curves(curves):
    idle_curve = [{}]

    return dict(
        (name, value) for (name, value) in curves.items()
        if value.get('options', idle_curve) != idle_curve
    )
