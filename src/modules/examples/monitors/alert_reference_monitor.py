import re

from live_client.utils import logging
from live_client.query import on_event

from setproctitle import setproctitle
from ddg.search import DuckEngine
from .base import Monitor

__all__ = ["start"]

READ_TIMEOUT = 120


def clean_term(term):
    m = re.search(r"\w+", term)
    if m is None:
        return None
    return m.group(0)


class AlertReferenceMonitor(Monitor):
    monitor_name = "alert_reference_monitor"

    def run(self):
        logging.info("{}: Alert Reference Monitor".format(self.process_name))
        setproctitle('DDA: Alert Reference Monitor "{}"'.format(self.process_name))

        alert_query = "__annotations __src:rulealert"
        span = self.settings["monitor"].get("span")

        @on_event(alert_query, self.settings, span=span, timeout=READ_TIMEOUT)
        def handle_events(event):
            self.process_annotation(event)

        handle_events()

    def process_annotation(self, event):
        annotation_message = event["message"]
        search_term = self._extract_search_term(annotation_message)

        engine = DuckEngine()
        results = engine.search(search_term)
        message_lines = [
            f'References found for query "{annotation_message}":',
            f"Search term: {search_term}",
        ]
        if len(results) > 0:
            res = results[0]
            message_lines.append(f"{search_term}: <{res.url}|{res.desc}>")
        else:
            message_lines.append("No result found")
        message = "\n".join(message_lines)

        self.send_message(f"{message}", timestamp=event["timestamp"])

    def _extract_search_term(self, annotation_message):
        parts = annotation_message.split(":")
        part = parts[1] if len(parts) > 1 else parts[0]
        words = part.strip().split(" ")
        word = None
        for w in words:
            word = clean_term(w)
            if word is not None:
                break

        return word


def start(settings, task_id=None, **kwargs):
    AlertReferenceMonitor.start(settings, task_id, **kwargs)
