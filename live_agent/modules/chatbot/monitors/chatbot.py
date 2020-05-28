# -*- coding: utf-8 -*-
from multiprocessing import Queue, active_children
from functools import partial

from eliot import start_action
from setproctitle import setproctitle
from chatterbot.trainers import ChatterBotCorpusTrainer

from live_client import query
from live_client.events import messenger
from live_client.facades import LiveClient
from live_client.types.message import Message
from live_client.utils import logging

from live_agent.services.processes import agent_function

from live_agent.modules.chatbot.src.bot import ChatBot
from live_agent.modules.chatbot.src.actions import ActionStatement


__all__ = ["start"]

read_timeout = 120
request_timeout = (3.05, 5)


##
# Misc functions
def load_state(container, state_key=None, default=None):
    state = container.get("state", {})

    if state_key and (state_key not in state):
        if default is None:
            default = {}

        share_state(container, state_key=state_key, state_data=default)

    return state


def share_state(container, state_key=None, state_data=None):
    if "state" not in container:
        container.update(state={})

    container["state"].update(**{state_key: state_data})


##
# Chat message handling
def maybe_extract_messages(event):
    event_content = event.get("data", {}).get("content", [])

    return [
        Message(item)
        for item in event_content
        if (item.get("__type") == "__message") and (item.get("message") is not None)
    ]


def maybe_mention(settings, message):
    bot_alias = settings.get("alias", "Intelie")
    is_mention = message.has_mention(bot_alias)
    if is_mention:
        message = message.remove_mentions(bot_alias)

    return is_mention, message


def process_messages(chatbot, messages):
    settings = chatbot.context.get("settings")
    room_id = chatbot.context.get("room_id")

    for message in messages:
        with start_action(action_type="process_message", message=message.get("text")):
            is_mention, message = maybe_mention(settings, message)

            response = None
            if is_mention:
                response = chatbot.get_response(message)

            if response is not None:
                logging.info('Bot response is "{}"'.format(response.serialize()))
                if isinstance(response, ActionStatement):
                    response.chatbot = chatbot
                    response_message = response.run()
                else:
                    response_message = response.text

                maybe_send_message(settings, room_id, response_message)


def maybe_send_message(settings, room_id, response_message):
    bot_settings = settings.copy()
    bot_alias = bot_settings.get("alias", "Intelie")
    bot_settings["output"]["room"] = {"id": room_id}
    if "name" not in bot_settings["output"]["author"]:
        bot_settings["output"]["author"]["name"] = bot_alias

    messenger.send_message(
        response_message, settings=bot_settings, message_type=messenger.MESSAGE_TYPES.CHAT
    )


##
# Room Bot initialization
def train_bot(chatbot, language="english"):
    trainer = ChatterBotCorpusTrainer(chatbot)
    trainer.train(f"chatterbot.corpus.{language}.conversations")
    trainer.train(f"chatterbot.corpus.{language}.greetings")
    trainer.train(f"chatterbot.corpus.{language}.humor")


def start_chatbot(settings, room_id, room_queue, **kwargs):
    setproctitle("DDA: Chatbot for room {}".format(room_id))

    # Load the previous state
    state_manager = kwargs.get("state_manager")
    state = state_manager.load()

    settings.update(state=state.get("bot_state", {}))
    load_state_func = partial(load_state, settings)
    share_state_func = partial(share_state, settings)

    bot_alias = settings.get("alias", "Intelie")
    context = {
        "room_id": room_id,
        "settings": settings,
        "live_client": LiveClient(settings, room_id),
        "functions": {"load_state": load_state_func, "share_state": share_state_func},
    }
    chatbot = ChatBot(
        bot_alias,
        read_only=True,
        prefer_agreement=False,
        logic_adapters=settings.get("logic_adapters", []),
        preprocessors=["chatterbot.preprocessors.clean_whitespace"],
        filters=[],
        **context,
    )
    train_bot(chatbot)

    while True:
        event = room_queue.get()
        messages = maybe_extract_messages(event)
        process_messages(chatbot, messages)
        state_manager.save({"bot_state": settings.get("state", {})}, force=True)

    return chatbot


def add_bot(settings, bots_registry, room_id):
    new_bot = False
    if room_id is not None:
        room_bot, room_queue = bots_registry.get(room_id, (None, None))

        if room_bot and room_bot.is_alive():
            logging.debug("Bot for {} is already known".format(room_id))
        else:
            logging.info("New bot for room {}".format(room_id))
            new_bot = True

            start_chatbot_with_log = agent_function(
                start_chatbot, name=f"bot for room {room_id}", with_state=True
            )
            with start_action(action_type="start_chatbot", room_id=room_id) as action:
                task_id = action.serialize_task_id()
                room_queue = Queue()
                room_bot = start_chatbot_with_log(settings, room_id, room_queue, task_id=task_id)

            room_bot.start()
            bots_registry[room_id] = (room_bot, room_queue)

    return bots_registry, new_bot


def route_message(settings, bots_registry, event):
    logging.debug("Got an event: {}".format(event))

    messages = maybe_extract_messages(event)
    for message in messages:
        room_id = message.get("room", {}).get("id")
        sender = message.get("author", {})

        bots_registry, new_bot = add_bot(settings, bots_registry, room_id)
        if new_bot:
            messenger.add_to_room(settings, room_id, sender)

        # Send the message to the room's bot process
        room_bot, room_queue = bots_registry.get(room_id, (None, None))
        room_queue.put(event)

    return [item[0] for item in bots_registry.values()]


##
# Global process initialization
def start(settings, **kwargs):
    setproctitle("DDA: Chatbot main process")
    logging.info("Chatbot process started")

    # Load the previous state
    state_manager = kwargs.get("state_manager")
    state = state_manager.load()
    bots_registry = state.get("bots_registry", {})

    # Restart previously known bots
    rooms_with_bots = bots_registry.keys()
    for room_id in rooms_with_bots:
        bots_registry, new_bot = add_bot(settings, bots_registry, room_id)

    bot_alias = settings.get("alias", "Intelie").lower()
    bot_query = f"""
        __message -__delete:*
        => @filter(
            message:lower():contains("{bot_alias}") &&
            author->name:lower() != "{bot_alias}"
        )
    """

    @query.on_event(bot_query, settings, timeout=read_timeout)
    def handle_events(event, *args, **kwargs):
        messenger.join_messenger(settings)
        route_message(settings, bots_registry, event)

        # There is no use saving the processes, so we save a dict with no values
        state_manager.save(
            {"bots_registry": dict((room_id, (None, None)) for room_id in bots_registry)},
            force=True,
        )
        return

    try:
        handle_events()
    except Exception:
        # Nothing to do. Let this process end
        pass

    for bot in active_children():
        bot.terminate()
        bot.join(5)

    return
