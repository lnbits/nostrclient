
import asyncio
import ssl
import threading
import time

from loguru import logger

from .filter import Filters
from .message_pool import MessagePool, NoticeMessage
from .relay import Relay, RelayPolicy
from .subscription import Subscription


class RelayException(Exception):
    pass


class RelayManager:
    def __init__(self) -> None:
        self.relays: dict[str, Relay] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.queue_threads: dict[str, threading.Thread] = {}
        self.message_pool = MessagePool()
        self._cached_subscriptions: dict[str, Subscription] = {}
        self._subscriptions_lock = threading.Lock()

    def add_relay(self, url: str, read: bool = True, write: bool = True) -> Relay:
        if url in list(self.relays.keys()):
            return

        with self._subscriptions_lock:
            subscriptions = self._cached_subscriptions.copy()

        relay = Relay(url, self.message_pool, subscriptions)
        self.relays[url] = relay

        self._open_connection(
            relay,
            {"cert_reqs": ssl.CERT_NONE}
        )  # NOTE: This disables ssl certificate verification

        relay.publish_subscriptions()
        return relay

    def remove_relay(self, url: str):
        # try-catch?
        self.relays[url].close()
        self.relays.pop(url)
        self.threads[url].join(timeout=5)
        self.threads.pop(url)
        self.queue_threads[url].join(timeout=5)
        self.queue_threads.pop(url)

    def add_subscription(self, id: str, filters: Filters):
        with self._subscriptions_lock:
            self._cached_subscriptions[id] = Subscription(id, filters)

        for relay in self.relays.values():
            relay.add_subscription(id, filters)

    def close_subscription(self, id: str):
        with self._subscriptions_lock:
            self._cached_subscriptions.pop(id)

        for relay in self.relays.values():
            relay.close_subscription(id)

    def check_and_restart_relays(self):
        stopped_relays = [r for r in self.relays.values() if r.shutdown]
        for relay in stopped_relays:
            self._restart_relay(relay)

    def close_connections(self):
        for relay in self.relays.values():
            relay.close()

    def publish_message(self, message: str):
        for relay in self.relays.values():
                relay.publish(message)

    def handle_notice(self, notice: NoticeMessage):
        relay = next((r for r in self.relays.values() if r.url == notice.url))
        if relay:
            relay.add_notice(notice.content)

    def _open_connection(self, relay: Relay, ssl_options: dict = None, proxy: dict = None):
        self.threads[relay.url] = threading.Thread(
            target=relay.connect,
            args=(ssl_options, proxy),
            name=f"{relay.url}-thread",
            daemon=True,
        )
        self.threads[relay.url].start()

        def wrap_async_queue_worker():
            asyncio.run(relay.queue_worker())

        self.queue_threads[relay.url] = threading.Thread(
            target=wrap_async_queue_worker,
            name=f"{relay.url}-queue",
            daemon=True,
        )
        self.queue_threads[relay.url].start()

    def _restart_relay(self, relay: Relay):
        time_since_last_error = time.time() - relay.last_error_date

        min_wait_time = min(60 * relay.error_counter, 60 * 60 * 24) # try at least once a day
        if time_since_last_error < min_wait_time:
            return

        logger.info(f"Restarting connection to relay '{relay.url}'")

        self.remove_relay(relay.url)
        new_relay = self.add_relay(relay.url)
        new_relay.error_counter = relay.error_counter
        new_relay.error_list = relay.error_list
