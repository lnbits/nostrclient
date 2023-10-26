import asyncio
import json
from typing import List, Union

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from lnbits.helpers import urlsafe_short_hash

from . import nostr_client
from .models import Event, Filter
from .nostr.filter import Filter as NostrFilter
from .nostr.filter import Filters as NostrFilters
from .nostr.message_pool import EndOfStoredEventsMessage, NoticeMessage


class NostrRouter:
    received_subscription_events: dict[str, list[Event]] = {}
    received_subscription_notices: list[NoticeMessage] = []
    received_subscription_eosenotices: dict[str, EndOfStoredEventsMessage] = {}

    def __init__(self, websocket: WebSocket):
        self.subscriptions: List[str] = []
        self.connected: bool = True
        self.websocket: WebSocket = websocket
        self.tasks: List[asyncio.Task] = []  # chek why state is needed
        self.original_subscription_ids = {}  # here

    async def client_to_nostr(self):
        """
        Receives requests / data from the client and forwards it to relays. If the
        request was a subscription/filter, registers it with the nostr client lib.
        Remembers the subscription id so we can send back responses from the relay to this
        client in `nostr_to_client`
        """
        while self.connected:
            try:
                json_str = await self.websocket.receive_text()
            except WebSocketDisconnect:
                self.stop()
                break

            try:
                await self._handle_client_to_nostr(json_str)
            except Exception as e:
                logger.debug(f"Failed to handle client message: '{str(e)}'.")

    async def nostr_to_client(self):
        """
        Sends responses from relays back to the client. Polls the subscriptions of this client
        stored in `my_subscriptions`. Then gets all responses for this subscription id from `received_subscription_events` which
        is filled in tasks.py. Takes one response after the other and relays it back to the client. Reconstructs
        the reponse manually because the nostr client lib we're using can't do it. Reconstructs the original subscription id
        that we had previously rewritten in order to avoid collisions when multiple clients use the same id.
        """
        while self.connected:
            try:
                await self._handle_subscriptions()
                self._handle_notices()
            except Exception as e:
                logger.debug(f"Failed to handle response for client: '{str(e)}'.")
            await asyncio.sleep(0.1)

    async def start(self):
        self.connected = True
        self.tasks.append(asyncio.create_task(self.client_to_nostr()))
        self.tasks.append(asyncio.create_task(self.nostr_to_client()))

    def stop(self):
        for t in self.tasks:
            try:
                t.cancel()
            except Exception as _:
                pass

        for s in self.subscriptions:
            try:
                nostr_client.relay_manager.close_subscription(s)
            except Exception as _:
                pass

        try:
            self.websocket.close()
        except Exception as _:
            pass
        self.connected = False

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
                my_event = NostrRouter.received_subscription_events[s].pop(0)
                event_json = {
                    "id": my_event.id,
                    "pubkey": my_event.public_key,
                    "created_at": my_event.created_at,
                    "kind": my_event.kind,
                    "tags": my_event.tags,
                    "content": my_event.content,
                    "sig": my_event.signature,
                }

                # this reconstructs the original response from the relay
                # reconstruct original subscription id
                s_original = self.original_subscription_ids[s]
                event_to_forward = ["EVENT", s_original, event_json]
                await self.websocket.send_text(json.dumps(event_to_forward))
        except Exception as e:
            logger.debug(e)  # there are 2900 errors here

    def _handle_notices(self):
        while len(NostrRouter.received_subscription_notices):
            my_event = NostrRouter.received_subscription_notices.pop(0)
            #  note: we don't send it to the user because we don't know who should receive it
            logger.info(f"[Relay '{my_event.url}'] Notice: '{my_event.content}']")
            nostr_client.relay_manager.handle_notice(my_event)

    def _marshall_nostr_filters(self, data: Union[dict, list]):
        # todo: get rid of this
        filters = data if isinstance(data, list) else [data]
        filters = [Filter.parse_obj(f) for f in filters]
        filter_list: list[NostrFilter] = []
        for filter in filters:
            filter_list.append(
                NostrFilter(
                    event_ids=filter.ids,  # type: ignore
                    kinds=filter.kinds,  # type: ignore
                    authors=filter.authors,  # type: ignore
                    since=filter.since,  # type: ignore
                    until=filter.until,  # type: ignore
                    event_refs=filter.e,  # type: ignore
                    pubkey_refs=filter.p,  # type: ignore
                    limit=filter.limit,  # type: ignore
                )
            )
        return NostrFilters(filter_list)

    async def _handle_client_to_nostr(self, json_str):
        """Parses a (string) request from a client. If it is a subscription (REQ) or a CLOSE, it will
        register the subscription in the nostr client library that we're using so we can
        receive the callbacks on it later. Will rewrite the subscription id since we expect
        multiple clients to use the router and want to avoid subscription id collisions
        """

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
        subscription_id_rewritten = urlsafe_short_hash()
        self.original_subscription_ids[subscription_id_rewritten] = subscription_id
        fltr = json_data[2:]
        filters = self._marshall_nostr_filters(fltr)  # revisit

        nostr_client.relay_manager.add_subscription(subscription_id_rewritten, filters)
        request_rewritten = json.dumps([json_data[0], subscription_id_rewritten] + fltr)

        self.subscriptions.append(subscription_id_rewritten)  # why here also?
        nostr_client.relay_manager.publish_message(
            request_rewritten
        )  # both `add_subscription` and `publish_message`?

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
        else:
            logger.debug(f"Failed to unsubscribe from '{subscription_id}.'")
