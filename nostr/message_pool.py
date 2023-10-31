import json
from queue import Queue
from threading import Lock

from .message_type import RelayMessageType


class EventMessage:
    def __init__(self, event: str, event_id: str, subscription_id: str, url: str) -> None:
        self.event = event
        self.event_id = event_id
        self.subscription_id = subscription_id
        self.url = url


class NoticeMessage:
    def __init__(self, content: str, url: str) -> None:
        self.content = content
        self.url = url


class EndOfStoredEventsMessage:
    def __init__(self, subscription_id: str, url: str) -> None:
        self.subscription_id = subscription_id
        self.url = url


class MessagePool:
    def __init__(self) -> None:
        self.events: Queue[EventMessage] = Queue()
        self.notices: Queue[NoticeMessage] = Queue()
        self.eose_notices: Queue[EndOfStoredEventsMessage] = Queue()
        self._unique_events: set = set()
        self.lock: Lock = Lock()

    def add_message(self, message: str, url: str):
        self._process_message(message, url)

    def get_event(self):
        return self.events.get()

    def get_notice(self):
        return self.notices.get()

    def get_eose_notice(self):
        return self.eose_notices.get()

    def has_events(self):
        return self.events.qsize() > 0

    def has_notices(self):
        return self.notices.qsize() > 0

    def has_eose_notices(self):
        return self.eose_notices.qsize() > 0

    def _process_message(self, message: str, url: str):
        message_json = json.loads(message)
        message_type = message_json[0]
        if message_type == RelayMessageType.EVENT:
            subscription_id = message_json[1]
            event = message_json[2]
            if "id" not in event:
                return
            event_id = event["id"]

            with self.lock:
                if f"{subscription_id}_{event_id}" not in self._unique_events:
                    self._accept_event(EventMessage(json.dumps(event), event_id, subscription_id, url))
        elif message_type == RelayMessageType.NOTICE:
            self.notices.put(NoticeMessage(message_json[1], url))
        elif message_type == RelayMessageType.END_OF_STORED_EVENTS:
            self.eose_notices.put(EndOfStoredEventsMessage(message_json[1], url))

    def _accept_event(self, event_message: EventMessage):
        """
        Event uniqueness is considered per `subscription_id`.
        The `subscription_id` is rewritten to be unique and it is the same accross relays.
        The same event can come from different subscriptions (from the same client or from different ones).
        Clients that have joined later should receive older events.
        """
        self.events.put(event_message)
        self._unique_events.add(
            f"{event_message.subscription_id}_{event_message.event_id}"
        )
