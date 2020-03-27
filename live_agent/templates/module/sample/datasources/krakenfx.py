# -*- coding: utf-8 -*-
from setproctitle import setproctitle
import asyncio
import queue
import json
from multiprocessing import Process, Queue

import websockets
from eliot import start_action

from live_client.events import raw
from live_client.utils import logging

__all__ = ["start"]


async def read_results(url, pairs, output_queue):
    setproctitle("krakenfx: reading updates")
    with start_action(action_type="krakenfx.fetch_updates", url=url):
        # connect to the server
        async with websockets.connect(url) as websocket:
            subscription = {"event": "subscribe", "subscription": {"name": "trade"}, "pair": pairs}
            logging.info(f"Subscribing to '{subscription}'")
            await websocket.send(json.dumps(subscription))

            # listen for incoming messages
            async for message in websocket:
                logging.debug(f"New message'{message}'")
                output_queue.put(message)


def watch(url, pairs, output_queue):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(read_results(url, pairs, output_queue))


def get_trades(url, pairs):
    """
    We use a new process to consume the kraken api
    The goal is to isolate the `asyncio` code from the rest of the program
    """
    results_queue = Queue()
    process = Process(target=watch, args=(url, pairs, results_queue))
    process.start()
    return process, results_queue


def start(settings, **kwargs):
    """
    Monitors trades of a set of (crypto)currency pairs using `kraken.com` public api.

    For each trade detected, a new event is sent to live.
    """
    setproctitle("DDA: Currency trades datasource")

    # Input settings
    krakenfx_url = settings.get("krakenfx_url", "wss://ws.kraken.com/")
    pairs = settings.get("pairs", ["ETH/USD", "XBT/USD"])
    timeout = settings.get("timeout", 30)

    # Output settings
    event_type = settings.get("output", {}).get("event_type", "dda_crypto_trades")
    skipstorage = settings.get("output", {}).get("skipstorage", True)

    state_manager = kwargs.get("state_manager")
    state = state_manager.load()
    last_trades = state.get("last_trades", {})

    # A separate process is used to fetch data from kraken
    kraken_process, results_queue = get_trades(krakenfx_url, pairs)

    # Handle the events received from kraken
    while True:
        try:
            trade_data = json.loads(results_queue.get(timeout=timeout))
        except queue.Empty:
            logging.exception(f"No results after {timeout} seconds")
            break

        # We are only interested in trade events
        is_trade = isinstance(trade_data, list) and len(trade_data) == 4
        if is_trade:
            # Prepare an event
            channel_id, operation_data, operation_type, pair = trade_data
            operations = [
                {
                    "price": item[0],
                    "volume": item[1],
                    "time": item[2],
                    "side": item[3],
                    "orderType": item[4],
                    "misc": item[5],
                }
                for item in operation_data
            ]

            trade_event = {
                "channel_id": channel_id,
                "operations": operations,
                "operation_type": operation_type,
                "pair": pair,
                "__skipstorage": skipstorage,
            }

            # And send to live
            raw.create(event_type, trade_event, settings)

            # Update this datasource's state with the last trade for each pair
            # This might be useful if you needed to restore this state
            # when the datasource is restarted
            last_trades.update(pair=trade_event)
            state_manager.save({"last_trades": last_trades})

        else:
            logging.debug(f"Ignoring event {trade_data}")
            continue

    # Release resources on exit
    results_queue.close()
    kraken_process.terminate()
    kraken_process.join()
    return
