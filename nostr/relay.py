import json
import time
from queue import Queue
from threading import Lock
from typing import List

from loguru import logger
from websocket import WebSocketApp

from .event import Event
from .filter import Filters
from .message_pool import MessagePool
from .message_type import RelayMessageType
from .subscription import Subscription


class RelayPolicy:
    def __init__(self, should_read: bool = True, should_write: bool = True) -> None:
        self.should_read = should_read
        self.should_write = should_write

    def to_json_object(self) -> dict[str, bool]:
        return {"read": self.should_read, "write": self.should_write}


class Relay:
    def __init__(
        self,
        url: str,
        policy: RelayPolicy,
        message_pool: MessagePool,
        subscriptions: dict[str, Subscription] = {},
    ) -> None:
        self.url = url
        self.policy = policy
        self.message_pool = message_pool
        self.subscriptions = subscriptions
        self.connected: bool = False
        self.reconnect: bool = True
        self.shutdown: bool = False
        self.error_counter: int = 0
        self.error_threshold: int = 100
        self.error_list: List[str] = []
        self.num_received_events: int = 0
        self.num_sent_events: int = 0
        self.num_subscriptions: int = 0
        self.ssl_options: dict = {}
        self.proxy: dict = {}
        self.lock = Lock()
        self.queue = Queue()

    def connect(self, ssl_options: dict = None, proxy: dict = None):
        self.ws = WebSocketApp(
            self.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_ping=self._on_ping,
            on_pong=self._on_pong,
        )
        self.ssl_options = ssl_options
        self.proxy = proxy
        if not self.connected:
            self.ws.run_forever(
                sslopt=ssl_options,
                http_proxy_host=None if proxy is None else proxy.get("host"),
                http_proxy_port=None if proxy is None else proxy.get("port"),
                proxy_type=None if proxy is None else proxy.get("type"),
                ping_interval=5,
            )

    def close(self):
        self.ws.close()
        self.connected = False
        self.shutdown = True

    @property
    def error_threshold_reached(self):
        return self.error_threshold and self.error_counter > self.error_threshold

    @property
    def ping(self):
        ping_ms = int((self.ws.last_pong_tm - self.ws.last_ping_tm) * 1000)
        return ping_ms if self.connected and ping_ms > 0 else 0

    def publish(self, message: str):
        self.queue.put(message)

    def publish_subscriptions(self):
        for _, subscription in self.subscriptions.items():
            s = subscription.to_json_object()
            json_str = json.dumps(["REQ", s["id"], s["filters"][0]])
            self.publish(json_str)

    def queue_worker(self):
        while True:
            if self.connected:
                try:
                    message = self.queue.get(timeout=1)
                    self.num_sent_events += 1
                    self.ws.send(message)
                except Exception as e:
                    if self.shutdown:
                        logger.warning(f"Closing queue worker for '{self.url}'.")
                        break
            else:
                time.sleep(0.1)

    def add_subscription(self, id, filters: Filters):
        with self.lock:
            self.subscriptions[id] = Subscription(id, filters)

    def close_subscription(self, id: str) -> None:
        with self.lock:
            self.subscriptions.pop(id)
            self.publish(json.dumps(["CLOSE", id]))

    def to_json_object(self) -> dict:
        return {
            "url": self.url,
            "policy": self.policy.to_json_object(),
            "subscriptions": [
                subscription.to_json_object()
                for subscription in self.subscriptions.values()
            ],
        }

    def _on_open(self, _):
        logger.info(f"Connected to relay: '{self.url}'.")
        self.connected = True
        

    def _on_close(self, _, status_code, message):
        logger.warning(f"Connection to relay {self.url} closed. Status: '{status_code}'. Message: '{message}'.")
        self.close()

    def _on_message(self, _, message: str):
        if self._is_valid_message(message):
            self.num_received_events += 1
            self.message_pool.add_message(message, self.url)

    def _on_error(self, _, error):
        logger.warning(f"Relay error: '{str(error)}'")
        self._append_error_message(str(error))
        self.connected = False
        self.error_counter += 1

    def _on_ping(self, *_):
        return

    def _on_pong(self, *_):
        return

    def _is_valid_message(self, message: str) -> bool:
        message = message.strip("\n")
        if not message or message[0] != "[" or message[-1] != "]":
            return False

        message_json = json.loads(message)
        message_type = message_json[0]

        if not RelayMessageType.is_valid(message_type):
            return False
        
        if message_type == RelayMessageType.EVENT:
            return self._is_valid_event_message(message_json)
        
        if message_type == RelayMessageType.COMMAND_RESULT:
            return self._is_valid_command_result_message(message, message_json)

        return True

    def _is_valid_event_message(self, message_json):
        if not len(message_json) == 3:
            return False

        subscription_id = message_json[1]
        with self.lock:
            if subscription_id not in self.subscriptions:
                return False

        e = message_json[2]
        event = Event(
            e["content"],
            e["pubkey"],
            e["created_at"],
            e["kind"],
            e["tags"],
            e["sig"],
        )
        if not event.verify():
            return False

        with self.lock:
            subscription = self.subscriptions[subscription_id]

        if subscription.filters and not subscription.filters.match(event):
            return False
        
        return True
    
    def _is_valid_command_result_message(self, message,  message_json):
        if not len(message_json) < 3:
            return False
        
        if message_json[2] != True:
            logger.warning(f"Relay '{self.url}' negative command result: '{message}'")
            self._append_error_message(message)
            return False

        return True
    
    def _append_error_message(self, message):
        self.error_list = ([message] + self.error_list)[:20]