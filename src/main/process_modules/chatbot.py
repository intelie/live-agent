from multiprocessing import Process, Queue
from functools import partial

import queue

from chatbot_modules.constants import LOGIC_ADAPTERS
from chatterbot.trainers import ChatterBotCorpusTrainer
from dda.chatbot import ChatBot
from dda.chatbot.actions import ActionStatement
from eliot import start_action, preserve_context, Action
from live_client import query
from live_client.events import messenger, annotation, raw
from live_client.events.constants import EVENT_TYPE_EVENT
from live_client.facades import LiveClient
from live_client.types.message import Message
from live_client.utils.timestamp import get_timestamp
from live_client.utils import logging
from setproctitle import setproctitle


__all__ = ["start"]

read_timeout = 120
request_timeout = (3.05, 5)
max_retries = 5


##
# Misc functions
@preserve_context
def load_state(container, state_key=None, default=None):
    state = container.get("state", {})

    if state_key and (state_key not in state):
        if default is None:
            default = {}

        share_state(container, state_key=state_key, state_data=default)

    return state


@preserve_context
def share_state(container, state_key=None, state_data=None):
    if "state" not in container:
        container.update(state={})

    container["state"].update(**{state_key: state_data})


@preserve_context
def allow_extra_settings(func, *args, **kwargs):
    # Allow the caller to override some of the settings
    extra_settings = kwargs.pop("extra_settings", {})
    if extra_settings:
        process_settings = kwargs.get("process_settings", {})
        process_settings.update(extra_settings)
        kwargs["process_settings"] = process_settings

    return func(*args, **kwargs)


@preserve_context
def create_annotation(*args, **kwargs):
    return allow_extra_settings(annotation.create, *args, **kwargs)


@preserve_context
def send_message(*args, **kwargs):
    return allow_extra_settings(messenger.send_message, *args, **kwargs)


@preserve_context
def send_event(*args, **kwargs):
    return allow_extra_settings(raw.create, *args, **kwargs)


##
# Chat message handling
@preserve_context
def maybe_extract_messages(event):
    event_content = event.get("data", {}).get("content", [])

    return [
        Message(item)
        for item in event_content
        if (item.get("__type") == "__message") and (item.get("message") is not None)
    ]


@preserve_context
def maybe_mention(process_settings, message):
    bot_alias = process_settings.get("alias", "Intelie")
    is_mention = message.has_mention(bot_alias)
    if is_mention:
        message = message.remove_mentions(bot_alias)

    return is_mention, message


@preserve_context
def process_messages(chatbot, messages):
    process_name = chatbot.context.get('process_name')
    process_settings = chatbot.context.get('process_settings')
    output_info = chatbot.context.get('output_info')
    room_id = chatbot.context.get('room_id')

    for message in messages:
        with start_action(action_type="process_message", message=message.get("text")):
            is_mention, message = maybe_mention(process_settings, message)

            response = None
            if is_mention:
                response = chatbot.get_response(message)

            if response is not None:
                logging.info('{}: Bot response is "{}"'.format(process_name, response.serialize()))
                if isinstance(response, ActionStatement):
                    response.chatbot = chatbot
                    response_message = response.run()
                else:
                    response_message = response.text

                maybe_send_message(
                    process_name, process_settings, output_info, room_id, response_message
                )


@preserve_context
def maybe_send_message(process_name, process_settings, output_info, room_id, response_message):
    bot_settings = process_settings.copy()
    bot_alias = bot_settings.get("alias", "Intelie")
    bot_settings["destination"]["room"] = {"id": room_id}
    if "name" not in bot_settings["destination"]["author"]:
        bot_settings["destination"]["author"]["name"] = bot_alias

    messenger.send_message(
        process_name,
        response_message,
        get_timestamp(),
        process_settings=bot_settings,
        output_info=output_info,
        message_type=messenger.MESSAGE_TYPES.CHAT,
    )


##
# Room Bot initialization
@preserve_context
def train_bot(process_name, chatbot, language="english"):
    trainer = ChatterBotCorpusTrainer(chatbot)
    trainer.train(f"chatterbot.corpus.{language}.conversations")
    trainer.train(f"chatterbot.corpus.{language}.greetings")
    trainer.train(f"chatterbot.corpus.{language}.humor")


def start_chatbot(process_name, process_settings, output_info, room_id, room_queue, task_id):
    setproctitle("DDA: Chatbot for room {}".format(room_id))

    with Action.continue_task(task_id=task_id):
        process_settings.update(state={})
        load_state_func = partial(load_state, process_settings)
        share_state_func = partial(share_state, process_settings)

        # TODO: Replace these functions by an instance of LiveClient.
        run_query_func = partial(
            query.run,
            process_name,
            process_settings,
            timeout=request_timeout,
            max_retries=max_retries,
        )
        annotate_func = partial(
            create_annotation,
            process_settings=process_settings,
            output_info=output_info,
            room={"id": room_id},
        )
        messenger_func = partial(
            send_message,
            process_settings=process_settings,
            output_info=output_info,
            room={"id": room_id},
        )
        send_event_func = partial(
            send_event, process_settings=process_settings, output_info=output_info
        )

        bot_alias = process_settings.get("alias", "Intelie")
        context = {
            "functions": {
                "load_state": load_state_func,
                "share_state": share_state_func,
                "run_query": run_query_func,
                "create_annotation": annotate_func,
                "send_message": messenger_func,
                "send_event": send_event_func,
            },
            "process_name": process_name,
            "process_settings": process_settings,
            "output_info": output_info,
            "room_id": room_id,
        }
        liveclient = LiveClient(process_name, process_settings, output_info, room_id)
        chatbot = ChatBot(
            bot_alias,
            liveclient,
            filters=[],
            preprocessors=["chatterbot.preprocessors.clean_whitespace"],
            logic_adapters=LOGIC_ADAPTERS,
            read_only=True,
            **context,
        )
        train_bot(process_name, chatbot)

        while True:
            event = room_queue.get()
            messages = maybe_extract_messages(event)
            process_messages(chatbot, messages)

    return chatbot


@preserve_context
def route_message(process_name, process_settings, output_info, bots_registry, event):
    logging.debug("{}: Got an event: {}".format(process_name, event))

    messages = maybe_extract_messages(event)
    for message in messages:
        room_id = message.get("room", {}).get("id")
        sender = message.get("author", {})

        if room_id is None:
            return

        room_bot, room_queue = bots_registry.get(room_id, (None, None))

        if room_bot and room_bot.is_alive():
            logging.debug("{}: Bot for {} is already known".format(process_name, room_id))
        else:
            logging.info("{}: New bot for room {}".format(process_name, room_id))
            messenger.add_to_room(process_name, process_settings, output_info, room_id, sender)

            with start_action(action_type="start_chatbot", room_id=room_id) as action:
                task_id = action.serialize_task_id()
                room_queue = Queue()
                room_bot = Process(
                    target=start_chatbot,
                    args=(
                        process_name,
                        process_settings,
                        output_info,
                        room_id,
                        room_queue,
                        task_id,
                    ),
                )

            room_bot.start()
            bots_registry[room_id] = (room_bot, room_queue)

        # Send the message to the room's bot process
        room_queue.put(event)

    return [item[0] for item in bots_registry.values()]


##
# Global process initialization
def start(process_name, process_settings, output_info, _settings, task_id):
    setproctitle("DDA: Chatbot main process")

    with Action.continue_task(task_id=task_id):
        logging.info("{}: Chatbot process started".format(process_name))
        bots_registry = {}

        bot_alias = process_settings.get("alias", "Intelie").lower()
        bootstrap_query = f"""
            __message -__delete:*
            => @filter(
                message:lower():contains("{bot_alias}") &&
                author->name:lower() != "{bot_alias}"
            )
        """
        results_process, results_queue = query.run(
            process_name,
            process_settings,
            bootstrap_query,
            realtime=True,
            timeout=request_timeout,
            max_retries=max_retries,
        )

        while True:
            try:
                event = results_queue.get(timeout=read_timeout)
                messenger.join_messenger(process_name, process_settings, output_info)
            except queue.Empty as e:
                logging.exception(e)
                # [ECS]: FIXME: We should not do it recursive because python does not perform tail call optimization <<<<<
                start(process_name, process_settings, output_info, _settings, task_id)
                break

            event_type = event.get("data", {}).get("type")
            if event_type != EVENT_TYPE_EVENT:
                continue

            bot_processes = route_message(
                process_name, process_settings, output_info, bots_registry, event
            )

        results_process.join()
        for bot in bot_processes:
            bot.join()
    return
