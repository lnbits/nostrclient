import asyncio
import json
import time
from typing import ClassVar

from fastapi import WebSocket, WebSocketDisconnect
from lnbits.helpers import urlsafe_short_hash
from loguru import logger

from .nostr.client.client import NostrClient

# from . import nostr_client
from .nostr.message_pool import (
    CommandResultMessage,
    EndOfStoredEventsMessage,
    EventMessage,
    NoticeMessage,
)

nostr_client: NostrClient = NostrClient()
all_routers: list["NostrRouter"] = []

# How long to wait for relays to answer an EVENT before replying `OK false`.
PUBLISH_TIMEOUT_SECONDS = 10


class PendingPublish:
    """An EVENT a client sent that still awaits its `OK` reply."""

    def __init__(self, event_id: str, relay_count: int) -> None:
        self.event_id = event_id
        # relays connected at publish time; once this many answered we stop
        # waiting for an acceptance
        self.relay_count = relay_count
        self.sent_at = time.time()


class NostrRouter:
    received_subscription_events: ClassVar[dict[str, list[EventMessage]]] = {}
    received_subscription_notices: ClassVar[list[NoticeMessage]] = []
    received_subscription_eosenotices: ClassVar[dict[str, EndOfStoredEventsMessage]] = (
        {}
    )
    received_command_results: ClassVar[dict[str, list[CommandResultMessage]]] = {}

    def __init__(self, websocket: WebSocket):
        self.connected: bool = True
        self.websocket: WebSocket = websocket
        self.tasks: list[asyncio.Task] = []
        self.original_subscription_ids: dict[str, str] = {}
        self.pending_publishes: dict[str, PendingPublish] = {}

    @property
    def subscriptions(self) -> list[str]:
        return list(self.original_subscription_ids.keys())

    def start(self):
        self.connected = True
        self.tasks.append(asyncio.create_task(self._client_to_nostr()))
        self.tasks.append(asyncio.create_task(self._nostr_to_client()))

    async def stop(self):
        nostr_client.relay_manager.close_subscriptions(self.subscriptions)
        self.connected = False
        for event_id in self.pending_publishes:
            NostrRouter.received_command_results.pop(event_id, None)
        self.pending_publishes.clear()

        for t in self.tasks:
            try:
                t.cancel()
            except Exception as _:
                pass

        try:
            await self.websocket.close(reason="Websocket connection closed")
        except Exception as _:
            pass

    async def _client_to_nostr(self):
        """
        Receives requests / data from the client and forwards it to relays.
        """
        while self.connected:
            try:
                json_str = await self.websocket.receive_text()
            except WebSocketDisconnect as e:
                logger.debug(e)
                await self.stop()
                break

            try:
                await self._handle_client_to_nostr(json_str)
            except Exception as e:
                logger.debug(f"Failed to handle client message: '{e!s}'.")

    async def _nostr_to_client(self):
        """Sends responses from relays back to the client."""
        while self.connected:
            try:
                await self._handle_subscriptions()
                await self._handle_command_results()
                self._handle_notices()
            except Exception as e:
                logger.debug(f"Failed to handle response for client: '{e!s}'.")
                await asyncio.sleep(1)
            await asyncio.sleep(0.1)

    async def _handle_subscriptions(self):
        for s in self.subscriptions:
            if s in NostrRouter.received_subscription_events:
                await self._handle_received_subscription_events(s)
            if s in NostrRouter.received_subscription_eosenotices:
                await self._handle_received_subscription_eosenotices(s)

    async def _handle_received_subscription_eosenotices(self, s):
        try:
            if s not in self.original_subscription_ids:
                return
            s_original = self.original_subscription_ids[s]
            event_to_forward = ["EOSE", s_original]
            del NostrRouter.received_subscription_eosenotices[s]

            await self.websocket.send_text(json.dumps(event_to_forward))
        except Exception as e:
            logger.debug(e)

    async def _handle_received_subscription_events(self, s):
        try:
            if s not in NostrRouter.received_subscription_events:
                return

            while len(NostrRouter.received_subscription_events[s]):
                event_message = NostrRouter.received_subscription_events[s].pop(0)
                event_json = event_message.event

                # this reconstructs the original response from the relay
                # reconstruct original subscription id
                s_original = self.original_subscription_ids[s]
                event_to_forward = json.dumps(
                    ["EVENT", s_original, json.loads(event_json)]
                )
                await self.websocket.send_text(event_to_forward)
        except Exception as e:
            logger.warning(
                f"[NOSTRCLIENT] Error in _handle_received_subscription_events: {e}"
            )

    async def _handle_command_results(self):
        """
        Reply exactly one `["OK", <id>, <accepted>, <message>]` per EVENT a
        client published (NIP-01). The EVENT was fanned out to every relay, so
        several OKs can come back for one id: the client gets `true` as soon
        as any relay accepts, and `false` once every relay has rejected it or
        the wait times out.
        """
        for event_id in list(self.pending_publishes.keys()):
            pending = self.pending_publishes[event_id]
            results = NostrRouter.received_command_results.get(event_id, [])
            accepted = next((r for r in results if r.accepted), None)
            if accepted:
                await self._send_ok(event_id, True, accepted.message)
            elif len(results) >= pending.relay_count:
                await self._send_ok(event_id, False, results[-1].message)
            elif time.time() - pending.sent_at > PUBLISH_TIMEOUT_SECONDS:
                message = (
                    results[-1].message
                    if results
                    else "error: timed out waiting for relays"
                )
                await self._send_ok(event_id, False, message)
            else:
                continue
            self.pending_publishes.pop(event_id, None)
            NostrRouter.received_command_results.pop(event_id, None)

    async def _send_ok(self, event_id: str, accepted: bool, message: str):
        try:
            await self.websocket.send_text(
                json.dumps(["OK", event_id, accepted, message])
            )
        except Exception as e:
            logger.debug(f"Failed to send OK for '{event_id}': {e}")

    def _handle_notices(self):
        while len(NostrRouter.received_subscription_notices):
            my_event = NostrRouter.received_subscription_notices.pop(0)
            logger.debug(f"[Relay '{my_event.url}'] Notice: '{my_event.content}']")
            #  Note: we don't send it to the user because
            #  we don't know who should receive it
            nostr_client.relay_manager.handle_notice(my_event)

    async def _handle_client_to_nostr(self, json_str):
        json_data = json.loads(json_str)
        assert len(json_data), "Bad JSON array"

        if json_data[0] == "REQ":
            await self._handle_client_req(json_data)
            return

        if json_data[0] == "CLOSE":
            self._handle_client_close(json_data[1])
            return

        if json_data[0] == "EVENT":
            await self._handle_client_event(json_data, json_str)
            return

    async def _handle_client_event(self, json_data, json_str):
        event = json_data[1] if len(json_data) > 1 else None
        event_id = event.get("id") if isinstance(event, dict) else None
        if not event_id:
            logger.debug("Ignoring EVENT without an id.")
            return

        connected = [
            r for r in nostr_client.relay_manager.relays.values() if r.connected
        ]
        if not connected:
            await self._send_ok(event_id, False, "error: no relays connected")
            return

        self.pending_publishes[event_id] = PendingPublish(event_id, len(connected))
        nostr_client.relay_manager.publish_message(json_str)

    async def _handle_client_req(self, json_data):
        subscription_id = json_data[1]
        logger.info(f"New subscription: '{subscription_id}'")
        if not nostr_client.relay_manager.relays:
            # NIP-01: nothing will ever serve this subscription, so refuse it.
            # Only when no relay is configured at all: a configured relay that
            # is merely reconnecting gets the cached subscription replayed.
            await self._send_closed(subscription_id, "error: no relay connections")
            return
        subscription_id_rewritten = urlsafe_short_hash()
        self.original_subscription_ids[subscription_id_rewritten] = subscription_id
        filters = json_data[2:]

        nostr_client.relay_manager.add_subscription(subscription_id_rewritten, filters)

    async def _send_closed(self, subscription_id: str, message: str):
        try:
            await self.websocket.send_text(
                json.dumps(["CLOSED", subscription_id, message])
            )
        except Exception as e:
            logger.debug(f"Failed to send CLOSED for '{subscription_id}': {e}")

    def _handle_client_close(self, subscription_id):
        subscription_id_rewritten = next(
            (
                k
                for k, v in self.original_subscription_ids.items()
                if v == subscription_id
            ),
            None,
        )
        if subscription_id_rewritten:
            self.original_subscription_ids.pop(subscription_id_rewritten)
            nostr_client.relay_manager.close_subscription(subscription_id_rewritten)
            logger.info(
                f"""
            Unsubscribe from '{subscription_id_rewritten}'.
            Original id: '{subscription_id}.'
            """
            )
        else:
            logger.info(f"Failed to unsubscribe from '{subscription_id}.'")
