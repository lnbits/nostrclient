import json
import time
from queue import Queue

from loguru import logger

from .message_pool import MessagePool
from .subscription import Subscription


class Relay:
    def __init__(self, url: str, message_pool: MessagePool) -> None:
        self.url = url
        self.message_pool = message_pool
        self.connected: bool = False
        self.reconnect: bool = True
        self.shutdown: bool = False

        self.error_counter: int = 0
        self.error_threshold: int = 100
        self.error_list: list[str] = []
        self.notice_list: list[str] = []
        self.last_error_date: int = 0
        self.num_received_events: int = 0
        self.num_sent_events: int = 0
        self.num_subscriptions: int = 0
        self.queue: Queue = Queue()

    def connect(self):
        logger.warning(
            "nostr.relay.Relay is a legacy compatibility shim. "
            "Use nostr.relay_manager.RelayManager for SDK-backed relay IO."
        )
        self.connected = True
        self.shutdown = False

    def close(self):
        self.connected = False
        self.shutdown = True

    @property
    def error_threshold_reached(self):
        return self.error_threshold and self.error_counter >= self.error_threshold

    @property
    def ping(self):
        return 0

    def publish(self, message: str):
        self.queue.put(message)
        self.num_sent_events += 1

    def publish_subscriptions(self, subscriptions: list[Subscription]):
        for s in subscriptions:
            assert s.filters
            self.publish(json.dumps(["REQ", s.id, *s.filters]))

    async def queue_worker(self):
        return

    def close_subscription(self, sub_id: str) -> None:
        self.publish(json.dumps(["CLOSE", sub_id]))

    def add_notice(self, notice: str):
        self.notice_list = [notice, *self.notice_list]

    def _append_error_message(self, message):
        self.error_counter += 1
        self.error_list = [message, *self.error_list]
        self.last_error_date = int(time.time())
