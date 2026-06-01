import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from nostr_sdk import (
    Client,
    ClientMessage,
    HandleNotification,
    RelayMessage,
    RelayUrl,
    uniffi_set_event_loop,
)
from nostr_sdk import (
    Relay as SdkRelay,
)
from nostr_sdk import (
    RelayStatus as SdkRelayStatus,
)

from .message_pool import MessagePool, NoticeMessage


@dataclass
class RelayConnection:
    url: str
    relay: SdkRelay | None = None
    connected: bool = False
    reconnect: bool = True
    shutdown: bool = False
    error_counter: int = 0
    error_threshold: int = 100
    error_list: list[str] = field(default_factory=list)
    notice_list: list[str] = field(default_factory=list)
    last_error_date: int = 0
    num_received_events: int = 0
    num_sent_events: int = 0
    num_subscriptions: int = 0
    ping: int = 0

    def close(self) -> None:
        self.connected = False
        self.shutdown = True

    def add_notice(self, notice: str) -> None:
        self.notice_list = [notice, *self.notice_list][:50]

    def append_error(self, message: str) -> None:
        self.error_counter += 1
        self.last_error_date = int(time.time())
        self.error_list = [message, *self.error_list][:50]

    def update_from_sdk(self, relay: SdkRelay | None) -> None:
        self.relay = relay
        if relay is None:
            self.connected = False
            self.shutdown = True
            self.ping = 0
            return

        status = relay.status()
        self.connected = status == SdkRelayStatus.CONNECTED
        self.shutdown = status in {SdkRelayStatus.TERMINATED, SdkRelayStatus.BANNED}

        try:
            latency = relay.stats().latency()
            self.ping = int(latency.total_seconds() * 1000) if latency else 0
        except Exception:
            self.ping = 0


class _NotificationHandler(HandleNotification):
    def __init__(self, relay_manager: "RelayManager") -> None:
        self.relay_manager = relay_manager

    async def handle_msg(self, relay_url: RelayUrl, msg: RelayMessage) -> None:
        url = str(relay_url)
        relay = self.relay_manager._ensure_relay_state(url)
        relay.update_from_sdk(await self.relay_manager._get_sdk_relay(url))

        try:
            message_json = msg.as_json()
            message_enum = msg.as_enum()
        except Exception as exc:
            relay.append_error(f"Failed to parse relay message: {exc!s}")
            return

        if message_enum.is_NOTICE():
            relay.add_notice(message_enum.message)
            self.relay_manager.message_pool.add_message(message_json, url)
            return

        if message_enum.is_END_OF_STORED_EVENTS():
            self.relay_manager.message_pool.add_message(message_json, url)
            return

        if getattr(message_enum, "is_CLOSED", lambda: False)():
            relay.append_error(getattr(message_enum, "message", "Subscription closed."))

    async def handle(
        self, relay_url: RelayUrl, subscription_id: str, event: Any
    ) -> None:
        url = str(relay_url)
        relay = self.relay_manager._ensure_relay_state(url)
        relay.num_received_events += 1
        relay.update_from_sdk(await self.relay_manager._get_sdk_relay(url))
        self.relay_manager.message_pool.add_message(
            RelayMessage.event(subscription_id, event).as_json(),
            url,
        )


class RelayManager:
    def __init__(self) -> None:
        self.relays: dict[str, RelayConnection] = {}
        self.message_pool = MessagePool()
        self._cached_subscriptions: dict[str, list[Any]] = {}
        self._subscriptions_lock = threading.Lock()
        self._loop_ready = threading.Event()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="nostrclient-sdk",
            daemon=True,
        )
        self._thread.start()
        self._loop_ready.wait(timeout=10)

    def add_relay(self, url: str) -> RelayConnection:
        if url in self.relays:
            logger.debug(f"Relay '{url}' already present.")
            return self.relays[url]

        relay = self._ensure_relay_state(url)
        self._run_coro(self._add_relay(url))
        return relay

    def remove_relay(self, url: str) -> None:
        relay = self.relays.get(url)
        if relay:
            relay.close()
        self._run_coro(self._remove_relay(url), suppress=True)
        self.relays.pop(url, None)

    def remove_relays(self) -> None:
        for url in list(self.relays.keys()):
            self.remove_relay(url)

    def add_subscription(self, subscription_id: str, filters: list[Any]) -> None:
        with self._subscriptions_lock:
            self._cached_subscriptions[subscription_id] = filters

        self._run_coro(
            self._broadcast_subscription(subscription_id, filters),
            suppress=True,
        )
        self._refresh_subscription_counts()

    def close_subscription(self, subscription_id: str) -> None:
        logger.info(f"Closing subscription: '{subscription_id}'.")
        with self._subscriptions_lock:
            self._cached_subscriptions.pop(subscription_id, None)
        self._run_coro(self._close_subscription(subscription_id), suppress=True)
        self._refresh_subscription_counts()

    def close_subscriptions(self, subscriptions: list[str]) -> None:
        for subscription_id in subscriptions:
            self.close_subscription(subscription_id)

    def close_all_subscriptions(self) -> None:
        self.close_subscriptions(list(self._cached_subscriptions.keys()))

    def check_and_restart_relays(self) -> None:
        self._run_coro(self._reconnect_stale_relays(), suppress=True)

    def close_connections(self) -> None:
        self._run_coro(self._disconnect_all(), suppress=True)
        for relay in self.relays.values():
            relay.connected = False
            relay.shutdown = True

    def shutdown(self) -> None:
        if self._closed:
            return
        self.close_all_subscriptions()
        self.close_connections()

        async def _shutdown() -> None:
            current = asyncio.current_task()
            for task in list(asyncio.all_tasks(self._loop)):
                if task is current:
                    continue
                task.cancel()
            await asyncio.sleep(0)
            self._loop.stop()

        self._submit_coro(_shutdown(), suppress=True)
        self._closed = True
        self._thread.join(timeout=5)

    def publish_message(self, message: str) -> None:
        self._run_coro(self._publish_message(message), suppress=True)

    def handle_notice(self, notice: NoticeMessage) -> None:
        relay = self.relays.get(notice.url)
        if relay:
            relay.add_notice(notice.content)

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        uniffi_set_event_loop(self._loop)
        self._client = Client()
        self._handler = _NotificationHandler(self)
        self._notification_task = self._loop.create_task(
            self._client.handle_notifications(self._handler)
        )
        self._loop_ready.set()
        self._loop.run_forever()
        self._loop.close()

    def _run_coro(self, coro: Any, suppress: bool = False) -> Any:
        if self._closed or not self._loop_ready.is_set():
            return None
        return self._submit_coro(coro, suppress=suppress)

    def _submit_coro(self, coro: Any, suppress: bool = False) -> Any:
        if not self._loop_ready.is_set():
            return None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=15)
        except Exception as exc:
            if suppress:
                logger.debug(f"[nostrclient] Background SDK call failed: {exc!s}")
                return None
            raise

    def _ensure_relay_state(self, url: str) -> RelayConnection:
        relay = self.relays.get(url)
        if relay:
            return relay
        relay = RelayConnection(url=url)
        self.relays[url] = relay
        self._refresh_subscription_counts()
        return relay

    def _refresh_subscription_counts(self) -> None:
        count = len(self._cached_subscriptions)
        for relay in self.relays.values():
            relay.num_subscriptions = count

    async def _add_relay(self, url: str) -> None:
        relay_url = RelayUrl.parse(url)
        await self._client.add_relay(relay_url)
        await self._client.connect_relay(relay_url)
        relay = self._ensure_relay_state(url)
        relay.update_from_sdk(await self._get_sdk_relay(url))
        await self._replay_cached_subscriptions([relay_url])

    async def _remove_relay(self, url: str) -> None:
        relay_url = RelayUrl.parse(url)
        await self._client.force_remove_relay(relay_url)

    async def _broadcast_subscription(
        self, subscription_id: str, filters: list[Any]
    ) -> None:
        if not self.relays:
            return
        message = self._req_message(subscription_id, filters)
        await self._send_to_relays(list(self.relays.keys()), message)
        for relay in self.relays.values():
            relay.num_sent_events += 1

    async def _close_subscription(self, subscription_id: str) -> None:
        await self._client.unsubscribe(subscription_id)
        if not self.relays:
            return
        message = ClientMessage.close(subscription_id)
        await self._send_to_relays(list(self.relays.keys()), message)
        for relay in self.relays.values():
            relay.num_sent_events += 1

    async def _publish_message(self, message: str) -> None:
        if not self.relays:
            return
        client_message = ClientMessage.from_json(message)
        await self._send_to_relays(list(self.relays.keys()), client_message)
        for relay in self.relays.values():
            relay.num_sent_events += 1

    async def _disconnect_all(self) -> None:
        await self._client.disconnect()

    async def _reconnect_stale_relays(self) -> None:
        sdk_relays = await self._client.relays()
        for relay_url, sdk_relay in sdk_relays.items():
            url = str(relay_url)
            relay = self._ensure_relay_state(url)
            relay.update_from_sdk(sdk_relay)
            if sdk_relay.status() in {
                SdkRelayStatus.INITIALIZED,
                SdkRelayStatus.TERMINATED,
            }:
                try:
                    await self._client.connect_relay(relay_url)
                except Exception as exc:
                    relay.append_error(str(exc))

    async def _replay_cached_subscriptions(self, relay_urls: list[RelayUrl]) -> None:
        with self._subscriptions_lock:
            cached = list(self._cached_subscriptions.items())
        for subscription_id, filters in cached:
            message = self._req_message(subscription_id, filters)
            await self._client.send_msg_to(relay_urls, message)

    async def _send_to_relays(
        self, relay_urls: list[str], message: ClientMessage
    ) -> None:
        if not relay_urls:
            return
        await self._client.send_msg_to(
            [RelayUrl.parse(url) for url in relay_urls],
            message,
        )

    async def _get_sdk_relay(self, url: str) -> SdkRelay | None:
        relays = await self._client.relays()
        for relay_url, relay in relays.items():
            if str(relay_url) == url:
                return relay
        return None

    def _req_message(self, subscription_id: str, filters: list[Any]) -> ClientMessage:
        return ClientMessage.from_json(json.dumps(["REQ", subscription_id, *filters]))
