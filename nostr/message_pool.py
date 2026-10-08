import json
from queue import Queue
from threading import Lock

from .message_type import RelayMessageType


class EventMessage:
    def __init__(
        self, event: str, event_id: str, subscription_id: str, url: str
    ) -> None:
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
        # Event IDs seen per open subscription. Messages for subscriptions that
        # are not open are dropped, so this state is bounded by open subscriptions.
        self._subscription_events: dict[str, set[str]] = {}
        self.lock: Lock = Lock()

    def add_message(self, message: str, url: str):
        self._process_message(message, url)

    def open_subscription(self, subscription_id: str) -> None:
        with self.lock:
            self._subscription_events.setdefault(subscription_id, set())

    def close_subscription(self, subscription_id: str) -> None:
        with self.lock:
            self._subscription_events.pop(subscription_id, None)

    def is_subscription_open(self, subscription_id: str) -> bool:
        with self.lock:
            return subscription_id in self._subscription_events

    def tracked_event_count(self) -> int:
        with self.lock:
            return sum(len(ids) for ids in self._subscription_events.values())

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
                # Event uniqueness is considered per `subscription_id`. The
                # `subscription_id` is rewritten to be unique and it is the same
                # across relays. The same event can come from different
                # subscriptions (from the same client or from different ones).
                seen = self._subscription_events.get(subscription_id)
                if seen is None or event_id in seen:
                    return
                seen.add(event_id)
                self.events.put(
                    EventMessage(json.dumps(event), event_id, subscription_id, url)
                )
        elif message_type == RelayMessageType.NOTICE:
            self.notices.put(NoticeMessage(message_json[1], url))
        elif message_type == RelayMessageType.END_OF_STORED_EVENTS:
            subscription_id = message_json[1]
            if self.is_subscription_open(subscription_id):
                self.eose_notices.put(EndOfStoredEventsMessage(subscription_id, url))
