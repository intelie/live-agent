# -*- coding: utf-8 -*-
import logging
from multiprocessing import Process
from functools import partial
from chatterbot import ChatBot
from chatterbot.trainers import ChatterBotCorpusTrainer
from setproctitle import setproctitle

from live_client import query
from live_client.events import messenger
from live_client.utils.timestamp import get_timestamp


__all__ = ['start']


##
# Chat message handling
def maybe_extract_messages(event):
    event_content = event.get('data', {}).get('content', [])
    return filter(
        lambda item: (item.get('__type') == '__message') and (item.get('message') is not None),
        event_content
    )


def process_messages(process_name, process_settings, output_info, room_id, chatbot, messages):
    for message in messages:
        is_mention, message_text = maybe_mention(process_settings, message)

        shared_state = process_settings.get('state', {})
        response = chatbot.get_response(
            message_text,
            additional_response_selection_parameters=shared_state
        )

        if response and (is_mention or response.confidence >= 0.75):
            logging.info('{}: Bot response is "{}"'.format(process_name, response.serialize()))
            maybe_send_message(
                process_name,
                process_settings,
                output_info,
                room_id,
                response
            )
            process_settings.update(state=shared_state)

    messenger.join_room(process_name, process_settings, output_info)


def maybe_send_message(process_name, process_settings, output_info, room_id, bot_response):
    bot_settings = process_settings.copy()
    bot_alias = bot_settings.get('alias', 'Intelie')
    bot_settings['destination']['room'] = {'id': room_id}
    bot_settings['destination']['author']['name'] = bot_alias

    messenger.send_message(
        process_name,
        bot_response.text,
        get_timestamp(),
        process_settings=bot_settings,
        output_info=output_info,
        message_type=messenger.MESSAGE_TYPES.CHAT,
    )


def maybe_mention(process_settings, message):
    bot_alias = process_settings.get('alias', 'Intelie')
    message_text = message.get('message')
    is_mention = bot_alias in message_text
    if is_mention:
        message_text = message_text.replace(bot_alias, '')

    return is_mention, message_text


##
# Room Bot initialization
def train_bot(process_name, chatbot):
    trainer = ChatterBotCorpusTrainer(chatbot)
    trainer.train('chatterbot.corpus.english.conversations')
    trainer.train('chatterbot.corpus.english.greetings')
    trainer.train('chatterbot.corpus.english.humor')
    # trainer.train('chatterbot.corpus.portuguese.conversations')
    # trainer.train('chatterbot.corpus.portuguese.greetings')


def start_chatbot(process_name, process_settings, output_info, room_id, sender, first_message):
    setproctitle('DDA: Chatbot for room {}'.format(room_id))
    run_query_func = partial(query.run, process_name, process_settings)

    bot_alias = process_settings.get('alias', 'Intelie')
    messenger.add_to_room(process_name, process_settings, output_info, room_id, sender)
    chatbot = ChatBot(
        bot_alias,
        filters=[],
        preprocessors=[
            'chatterbot.preprocessors.clean_whitespace'
        ],
        logic_adapters=[
            {
                'import_path': 'chatterbot.logic.BestMatch',
                'default_response': 'I am sorry, but I do not understand.',
                'maximum_similarity_threshold': 0.90
            },
            'chatbot_modules.live_asset.AssetListAdapter',
            'chatbot_modules.live_asset.AssetSelectionAdapter',
            'chatbot_modules.pipes_query.CurrentValueAdapter',
        ],
        read_only=True,
        functions={
            'run_query': run_query_func,
        },
        env={
            'process_name': process_name,
            'process_settings': process_settings,
            'output_info': output_info,
            'room_id': room_id,
        }
    )
    train_bot(process_name, chatbot)

    room_query_template = '(__message|__annotations) => @filter room->id=="{}" && author->name!="{}"'
    room_query = room_query_template.format(room_id, bot_alias)

    results_process, results_queue = run_query_func(
        room_query,
        realtime=True,
    )

    messenger.join_room(process_name, process_settings, output_info)

    process_messages(
        process_name,
        process_settings,
        output_info,
        room_id,
        chatbot,
        [first_message]
    )

    while True:
        event = results_queue.get()
        messages = maybe_extract_messages(event)
        process_messages(
            process_name,
            process_settings,
            output_info,
            room_id,
            chatbot,
            messages
        )

    return chatbot


def process_bootstrap_message(process_name, process_settings, output_info, bots_registry, event):
    logging.debug("{}: Got an event: {}".format(process_name, event))

    messages = maybe_extract_messages(event)
    for message in messages:
        room_id = message.get('room', {}).get('id')
        sender = message.get('author', {})

        if room_id is None:
            return

        if room_id in bots_registry and bots_registry[room_id].is_alive():
            logging.info("{}: Bot for {} is already known".format(process_name, room_id))

        else:
            logging.info("{}: New bot for room {}".format(process_name, room_id))
            bot_process = Process(
                target=start_chatbot,
                args=(process_name, process_settings, output_info, room_id, sender, message)
            )
            bot_process.start()
            bots_registry[room_id] = bot_process

    return bots_registry.values()


##
# Global process initialization
def start(process_name, process_settings, output_info, _settings):
    logging.info("{}: Chatbot process started".format(process_name))
    setproctitle('DDA: Chatbot main process')
    bots_registry = {}

    bot_alias = process_settings.get('alias', 'Intelie')

    bootstrap_query_template = '__message => @filter message:lower():contains("{}")'
    bootstrap_query = bootstrap_query_template.format(bot_alias.lower())

    results_process, results_queue = query.run(
        process_name,
        process_settings,
        bootstrap_query,
        realtime=True,
    )

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
