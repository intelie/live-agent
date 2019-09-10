# -*- coding: utf-8 -*-
from multiprocessing import Process
from functools import partial

from eliot import start_action, Action
from chatterbot import ChatBot
from chatterbot.trainers import ChatterBotCorpusTrainer
from setproctitle import setproctitle

from live_client import query
from live_client.events import messenger
from live_client.events.constants import EVENT_TYPE_EVENT
from live_client.types.message import Message
from live_client.utils.timestamp import get_timestamp

from chatbot_modules.constants import LOGIC_ADAPTERS
from utils import logging


__all__ = ['start']


##
# Misc functions
def load_state(container, state_key=None, default=None):
    state = container.get('state', {})

    if state_key and (state_key not in state):
        if default is None:
            default = {}

        share_state(container, state_key=state_key, state_data=default)

    return state


def share_state(container, state_key=None, state_data=None):
    if 'state' not in container:
        container.update(state={})

    container['state'].update(**{state_key: state_data})


##
# Chat message handling
def maybe_extract_messages(event):
    event_content = event.get('data', {}).get('content', [])

    return [
        Message(item)
        for item in event_content
        if (item.get('__type') == '__message') and (item.get('message') is not None)
    ]


def maybe_mention(process_settings, message):
    bot_alias = process_settings.get('alias', 'Intelie')
    is_mention = message.has_mention(bot_alias)
    if is_mention:
        message = message.remove_mentions(bot_alias)

    return is_mention, message


def process_messages(process_name, process_settings, output_info, room_id, chatbot, messages):
    for message in messages:
        with start_action(action_type=u"process_message", message=message.get('text')):
            is_mention, message = maybe_mention(process_settings, message)

            if is_mention:
                response = chatbot.get_response(message)
            else:
                response = None

            if response:
                logging.info('{}: Bot response is "{}"'.format(
                    process_name,
                    response.serialize()
                ))
                maybe_send_message(
                    process_name,
                    process_settings,
                    output_info,
                    room_id,
                    response
                )

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


##
# Room Bot initialization
def train_bot(process_name, chatbot, language='english'):
    trainer = ChatterBotCorpusTrainer(chatbot)
    trainer.train(f'chatterbot.corpus.{language}.conversations')
    trainer.train(f'chatterbot.corpus.{language}.greetings')
    trainer.train(f'chatterbot.corpus.{language}.humor')


def start_chatbot(process_name, process_settings, output_info, room_id, sender, first_message):
    setproctitle('DDA: Chatbot for room {}'.format(room_id))

    run_query_func = partial(query.run, process_name, process_settings)

    process_settings.update(state={})
    load_state_func = partial(load_state, process_settings)
    share_state_func = partial(share_state, process_settings)

    bot_alias = process_settings.get('alias', 'Intelie')
    messenger.add_to_room(process_name, process_settings, output_info, room_id, sender)
    chatbot = ChatBot(
        bot_alias,
        filters=[],
        preprocessors=[
            'chatterbot.preprocessors.clean_whitespace'
        ],
        logic_adapters=LOGIC_ADAPTERS,
        read_only=True,
        functions={
            'run_query': run_query_func,
            'load_state': load_state_func,
            'share_state': share_state_func,
        },
        process_name=process_name,
        process_settings=process_settings,
        output_info=output_info,
        room_id=room_id,
    )
    train_bot(process_name, chatbot)

    room_query_template = '__message => @filter room->id=="{}" && author->name!="{}"'
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

            with start_action(action_type=u"start_chatbot", room_id=room_id):
                bot_process = Process(
                    target=start_chatbot,
                    args=(process_name, process_settings, output_info, room_id, sender, message)
                )

            bot_process.start()
            bots_registry[room_id] = bot_process

    return bots_registry.values()


##
# Global process initialization
def start(process_name, process_settings, output_info, _settings, task_id):
    with Action.continue_task(task_id=task_id):
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
            event_type = event.get('data', {}).get('type')
            if event_type != EVENT_TYPE_EVENT:
                continue

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
