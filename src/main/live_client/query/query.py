# -*- coding: utf-8 -*-
import asyncio
from multiprocessing import Process, Queue

import requests
from eliot import start_action, Action
from setproctitle import setproctitle

from aiocometd import Client

from live_client.events.constants import EVENT_TYPE_DESTROY
from live_client.utils import logging


__all__ = [
    'run',
    'start',
    'watch',
]


def start(host, username, password, statement, realtime=False, span=None):
    session = requests.Session()
    session.auth = (username, password)

    api_url = '{}/rest/query'.format(host)
    query_payload = [{
        'provider': 'pipes',
        'preload': False,
        'span': span,
        'follow': realtime,
        'expression': statement
    }]

    r = session.post(api_url, json=query_payload)
    r.raise_for_status()

    channels = [
        item.get('channel')
        for item in r.json()
    ]

    return channels


async def read_results(url, channels, output_queue):
    setproctitle('DDA: cometd client for channels {}'.format(channels))

    # connect to the server
    async with Client(url) as client:
        # subscribe to channels to receive chat messages and
        # notifications about new members
        for channel in channels:
            await client.subscribe(channel)

        # listen for incoming messages
        async for message in client:
            output_queue.put(message)

            # Exit after the query has stopped
            event_data = message.get('data', {})
            event_type = event_data.get('type')
            if event_type == EVENT_TYPE_DESTROY:
                return


def watch(url, channels, output_queue, task_id):
    with Action.continue_task(task_id=task_id):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(read_results(url, channels, output_queue))


def run(process_name, process_settings, statement, realtime=False, span=None):
    with start_action(action_type=u"run_query", statement=statement) as action:
        task_id = action.serialize_task_id()
        live_settings = process_settings['live']
        host = live_settings['host']
        username = live_settings['username']
        password = live_settings['password']

        logging.info("{}: Query '{}' started".format(process_name, statement))
        channels = start(
            host,
            username,
            password,
            statement,
            realtime=realtime,
            span=span,
        )
        logging.info("{}: Results channel is {}".format(process_name, channels))

        host = live_settings['host']
        results_url = '{}/cometd'.format(host)

        events_queue = Queue()
        process = Process(target=watch, args=(results_url, channels, events_queue, task_id))
        process.start()

    return process, events_queue
