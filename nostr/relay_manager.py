import asyncio
import threading
import time
from typing import List

from loguru import logger

from .message_pool import MessagePool, NoticeMessage
from .relay import Relay
from .subscription import Subscription


class RelayManager:
    def __init__(self) -> None:
        self.relays: dict[str, Relay] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.queue_threads: dict[str, threading.Thread] = {}
        self.message_pool = MessagePool()
        self._cached_subscriptions: dict[str, Subscription] = {}
        self._subscriptions_lock = threading.Lock()

    def add_relay(self, url: str) -> Relay:
        if url in list(self.relays.keys()):
            logger.debug(f"Relay '{url}' already present.")
            return self.relays[url]

        relay = Relay(url, self.message_pool)
        self.relays[url] = relay

        self._open_connection(relay)

        relay.publish_subscriptions(list(self._cached_subscriptions.values()))
        return relay

    def remove_relay(self, url: str):
        try:
            self.relays[url].close()
        except Exception as e:
            logger.debug(e)

        if url in self.relays:
            self.relays.pop(url)

        try:
            self.threads[url].join(timeout=5)
        except Exception as e:
            logger.debug(e)

        if url in self.threads:
            self.threads.pop(url)

        try:
            self.queue_threads[url].join(timeout=5)
        except Exception as e:
            logger.debug(e)

        if url in self.queue_threads:
            self.queue_threads.pop(url)

    def remove_relays(self):
        relay_urls = list(self.relays.keys())
        for url in relay_urls:
            self.remove_relay(url)

    def add_subscription(self, id: str, filters: List[str]):
        s = Subscription(id, filters)
        with self._subscriptions_lock:
            self._cached_subscriptions[id] = s

        for relay in self.relays.values():
            relay.publish_subscriptions([s])

    def close_subscription(self, id: str):
        try:
            logger.info(f"Closing subscription: '{id}'.")
            with self._subscriptions_lock:
                if id in self._cached_subscriptions:
                    self._cached_subscriptions.pop(id)

            for relay in self.relays.values():
                relay.close_subscription(id)
        except Exception as e:
            logger.debug(e)

    def close_subscriptions(self, subscriptions: List[str]):
        for id in subscriptions:
            self.close_subscription(id)

    def close_all_subscriptions(self):
        all_subscriptions = list(self._cached_subscriptions.keys())
        self.close_subscriptions(all_subscriptions)

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

    def _open_connection(self, relay: Relay):
        self.threads[relay.url] = threading.Thread(
            target=relay.connect,
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

        min_wait_time = min(
            60 * relay.error_counter, 60 * 60
        )  # try at least once an hour
        if time_since_last_error < min_wait_time:
            return

        logger.info(f"Restarting connection to relay '{relay.url}'")

        self.remove_relay(relay.url)
        new_relay = self.add_relay(relay.url)
        new_relay.error_counter = relay.error_counter
        new_relay.error_list = relay.error_list
