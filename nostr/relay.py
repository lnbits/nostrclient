import asyncio
import json
import time
from queue import Queue
from typing import List

from loguru import logger
from websocket import WebSocketApp

from .message_pool import MessagePool
from .subscription import Subscription


class Relay:
    def __init__(self, url: str, message_pool: MessagePool) -> None:
        self.url = url
        self.message_pool = message_pool
        self.connected: bool = False
        self.reconnect: bool = True
        self.shutdown: bool = False
        # todo: extract stats
        self.error_counter: int = 0
        self.error_threshold: int = 100
        self.error_list: List[str] = []
        self.notice_list: List[str] = []
        self.last_error_date: int = 0
        self.num_received_events: int = 0
        self.num_sent_events: int = 0
        self.num_subscriptions: int = 0

        self.queue = Queue()

    def connect(self):
        self.ws = WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_ping=self._on_ping,
            on_pong=self._on_pong,
        )
        if not self.connected:
            self.ws.run_forever(ping_interval=10)

    def close(self):
        try:
            self.ws.close()
        except Exception as e:
            logger.warning(f"[Relay: {self.url}] Failed to close websocket: {e}")
        self.connected = False
        self.shutdown = True

    @property
    def error_threshold_reached(self):
        return self.error_threshold and self.error_counter >= self.error_threshold

    @property
    def ping(self):
        ping_ms = int((self.ws.last_pong_tm - self.ws.last_ping_tm) * 1000)
        return ping_ms if self.connected and ping_ms > 0 else 0

    def publish(self, message: str):
        self.queue.put(message)

    def publish_subscriptions(self, subscriptions: List[Subscription] = []):
        for subscription in subscriptions:
            s = subscription.to_json_object()
            json_str = json.dumps(["REQ", s["id"], s["filters"]])
            self.publish(json_str)

    async def queue_worker(self):
        while True:
            if self.connected:
                try:
                    message = self.queue.get(timeout=1)
                    self.num_sent_events += 1
                    self.ws.send(message)
                except:
                    pass
            else:
                await asyncio.sleep(1)

            if self.shutdown:
                logger.warning(f"[Relay: {self.url}] Closing queue worker.")
                return

    def close_subscription(self, id: str) -> None:
        self.publish(json.dumps(["CLOSE", id]))

    def add_notice(self, notice: str):
        self.notice_list = [notice] + self.notice_list

    def _on_open(self, _):
        logger.info(f"[Relay: {self.url}] Connected.")
        self.connected = True
        self.shutdown = False

    def _on_close(self, _, status_code, message):
        logger.warning(
            f"[Relay: {self.url}] Connection closed. Status: '{status_code}'. Message: '{message}'."
        )
        self.close()

    def _on_message(self, _, message: str):
        self.num_received_events += 1
        self.message_pool.add_message(message, self.url)

    def _on_error(self, _, error):
        logger.warning(f"[Relay: {self.url}] Error: '{str(error)}'")
        self._append_error_message(str(error))
        self.close()

    def _on_ping(self, *_):
        return

    def _on_pong(self, *_):
        return

    def _append_error_message(self, message):
        self.error_counter += 1
        self.error_list = [message] + self.error_list
        self.last_error_date = int(time.time())
