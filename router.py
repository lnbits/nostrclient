import asyncio
import json
from typing import ClassVar, Dict, List

from fastapi import WebSocket, WebSocketDisconnect
from lnbits.helpers import urlsafe_short_hash
from loguru import logger

from .nostr.client.client import NostrClient

# from . import nostr_client
from .nostr.message_pool import EndOfStoredEventsMessage, EventMessage, NoticeMessage

nostr_client: NostrClient = NostrClient()
all_routers: list["NostrRouter"] = []


class NostrRouter:
    received_subscription_events: ClassVar[dict[str, List[EventMessage]]] = {}
    received_subscription_notices: ClassVar[list[NoticeMessage]] = []
    received_subscription_eosenotices: ClassVar[dict[str, EndOfStoredEventsMessage]] = (
        {}
    )

    def __init__(self, websocket: WebSocket):
        self.connected: bool = True
        self.websocket: WebSocket = websocket
        self.tasks: List[asyncio.Task] = []
        self.original_subscription_ids: Dict[str, str] = {}

    @property
    def subscriptions(self) -> List[str]:
        return list(self.original_subscription_ids.keys())

    def start(self):
        self.connected = True
        self.tasks.append(asyncio.create_task(self._client_to_nostr()))
        self.tasks.append(asyncio.create_task(self._nostr_to_client()))

    async def stop(self):
        nostr_client.relay_manager.close_subscriptions(self.subscriptions)
        self.connected = False

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
                event_to_forward = f"""["EVENT", "{s_original}", {event_json}]"""
                await self.websocket.send_text(event_to_forward)
        except Exception as e:
            logger.debug(e)  # there are 2900 errors here

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
            self._handle_client_req(json_data)
            return

        if json_data[0] == "CLOSE":
            self._handle_client_close(json_data[1])
            return

        if json_data[0] == "EVENT":
            nostr_client.relay_manager.publish_message(json_str)
            return

    def _handle_client_req(self, json_data):
        subscription_id = json_data[1]
        logger.info(f"New subscription: '{subscription_id}'")
        subscription_id_rewritten = urlsafe_short_hash()
        self.original_subscription_ids[subscription_id_rewritten] = subscription_id
        filters = json_data[2:]

        nostr_client.relay_manager.add_subscription(subscription_id_rewritten, filters)

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
