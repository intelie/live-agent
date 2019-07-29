# -*- coding: utf-8 -*-
import logging
from multiprocessing import Process, Queue
from chatterbot import ChatBot
from chatterbot.trainers import ChatterBotCorpusTrainer

from live_client import query
from output_modules import messenger
from utils.timestamp import get_timestamp


__all__ = ['start']


def make_query(process_name, process_settings, statement, realtime=False, span=None):
    live_settings = process_settings['live']
    host = live_settings['host']
    username = live_settings['username']
    password = live_settings['password']

    logging.info("{}: Query '{}' started".format(process_name, statement))
    channels = query.start(
        host,
        username,
        password,
        statement,
        realtime=True,
        # span='last 30 minutes'
    )
    logging.info("{}: Results channel is {}".format(process_name, channels))

    return channels


def watch_results(process_name, process_settings, events_channel):
    live_settings = process_settings['live']
    host = live_settings['host']
    results_url = '{}/cometd'.format(host)

    events_queue = Queue()
    process = Process(target=query.watch, args=(results_url, events_channel, events_queue))
    process.start()

    return process, events_queue


def maybe_extract_messages(event):
    event_content = event.get('data', {}).get('content', [])
    return filter(
        lambda item: (item.get('__type') == '__message') and (item.get('message') is not None),
        event_content
    )


def maybe_send_message(process_name, process_settings, output_info, room_id, message):
    bot_settings = process_settings.copy()
    bot_alias = bot_settings.get('alias', 'Intelie')
    bot_settings['destination']['room'] = {'id': room_id}
    bot_settings['destination']['author']['name'] = bot_alias

    messenger.send_message(
        process_name,
        message,
        get_timestamp(),
        process_settings=bot_settings,
        output_info=output_info,
        message_type=messenger.MESSAGE_TYPES.CHAT,
    )


def start_chatbot(process_name, process_settings, output_info, room_id):
    bot_alias = process_settings.get('alias', 'Intelie')

    chatbot = ChatBot(
        bot_alias,
        preprocessors=[
            'chatterbot.preprocessors.clean_whitespace'
        ],
        logic_adapters=[
            'chatterbot.logic.MathematicalEvaluation',
            {
                'import_path': 'chatterbot.logic.BestMatch',
                'default_response': 'I am sorry, but I do not understand.',
                'maximum_similarity_threshold': 0.90
            }
        ]
    )
    maybe_send_message(
        process_name,
        process_settings,
        output_info,
        room_id,
        'Just one second..'
    )

    trainer = ChatterBotCorpusTrainer(chatbot)
    trainer.train('chatterbot.corpus.english')

    maybe_send_message(
        process_name,
        process_settings,
        output_info,
        room_id,
        'How can I help you?'
    )

    room_query_template = '(__message|__annotations) => @filter room->id=="{}" && author->name!="{}"'
    room_query = room_query_template.format(room_id, bot_alias)

    channels = make_query(
        process_name,
        process_settings,
        room_query,
        realtime=True,
        # span='last 30 minutes'
    )

    results_process, results_queue = watch_results(process_name, process_settings, channels)

    while True:
        event = results_queue.get()
        messages = maybe_extract_messages(event)

        for message in messages:
            message_text = message.get('message')
            response = chatbot.get_response(message_text)

            if response and (response.confidence >= 0.75):
                maybe_send_message(
                    process_name,
                    process_settings,
                    output_info,
                    room_id,
                    response.text
                )

    return chatbot


def start_room_bot(process_name, process_settings, output_info, room_id):
    bot_process = Process(
        target=start_chatbot,
        args=(process_name, process_settings, output_info, room_id)
    )
    bot_process.start()
    return bot_process


def process_bootstrap_message(process_name, process_settings, output_info, bots_registry, event):
    logging.debug("{}: Got an event: {}".format(process_name, event))

    messages = maybe_extract_messages(event)
    for message in messages:
        room_id = message.get('room', {}).get('id')

        if room_id is None:
            return

        if room_id not in bots_registry:
            logging.info("{}: New bot for room {}".format(process_name, room_id))
            bots_registry[room_id] = start_room_bot(
                process_name, process_settings, output_info, room_id
            )
        else:
            logging.info("{}: Bot for {} is already known".format(process_name, room_id))

    return bots_registry.values()


def start(process_name, process_settings, output_info, _settings):
    logging.info("{}: Chatbot process started".format(process_name))
    bots_registry = {}

    bot_alias = process_settings.get('alias', 'Intelie')

    bootstrap_query_template = '__message => @filter message:lower():contains("{}")'
    bootstrap_query = bootstrap_query_template.format(bot_alias.lower())

    channels = make_query(
        process_name,
        process_settings,
        bootstrap_query,
        realtime=True,
        # span='last 30 minutes'
    )

    results_process, results_queue = watch_results(process_name, process_settings, channels)

    while True:
        event = results_queue.get()
        bot_processes = process_bootstrap_message(
            process_name,
            process_settings,
            output_info,
            bots_registry,
            event
        )

    results_process.join()
    for bot in bot_processes:
        bot.join()

    return
