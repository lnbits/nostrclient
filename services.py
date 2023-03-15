import asyncio
import json
from typing import List, Union
from .models import RelayList, Relay, Event, Filter, Filters

from .nostr.event import Event as NostrEvent
from .nostr.filter import Filter as NostrFilter
from .nostr.filter import Filters as NostrFilters
from .tasks import (
    client,
    received_event_queue,
    received_subscription_events,
    received_subscription_eosenotices,
)
from fastapi import WebSocket, WebSocketDisconnect
from lnbits.helpers import urlsafe_short_hash


class NostrRouter:
    def __init__(self, websocket):
        self.subscriptions: List[str] = []
        self.connected: bool = True
        self.websocket = websocket
        self.tasks: List[asyncio.Task] = []
        self.subscription_id_rewrite: str = urlsafe_short_hash()

    async def client_to_nostr(self):
        """Receives requests / data from the client and forwards it to relays. If the
        request was a subscription/filter, registers it with the nostr client lib.
        Remembers the subscription id so we can send back responses from the relay to this
        client in `nostr_to_client`"""
        while True:
            try:
                json_str = await self.websocket.receive_text()
            except WebSocketDisconnect:
                self.connected = False
                break
            # print(json_str)

            # registers a subscription if the input was a REQ request
            subscription_id, json_str_rewritten = await self._add_nostr_subscription(
                json_str
            )
            if subscription_id and json_str_rewritten:
                self.subscriptions.append(subscription_id)
                json_str = json_str_rewritten

            # publish data
            client.relay_manager.publish_message(json_str)

    async def nostr_to_client(self):
        """Sends responses from relays back to the client. Polls the subscriptions of this client
        stored in `my_subscriptions`. Then gets all responses for this subscription id from `received_subscription_events` which
        is filled in tasks.py. Takes one response after the other and relays it back to the client. Reconstructs
        the reponse manually because the nostr client lib we're using can't do it. Reconstructs the original subscription id
        that we had previously rewritten in order to avoid collisions when multiple clients use the same id."""
        while True and self.connected:
            for s in self.subscriptions:
                if s in received_subscription_events:
                    while len(received_subscription_events[s]):
                        my_event = received_subscription_events[s].pop(0)
                        # event.to_message() does not include the subscription ID, we have to add it manually
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
                        # reconstruct oriiginal subscription id
                        s_original = s[len(f"{self.subscription_id_rewrite}_") :]
                        event_to_forward = ["EVENT", s_original, event_json]
                        # print(json.dumps(event_to_forward))

                        # send data back to client
                        await self.websocket.send_text(json.dumps(event_to_forward))
                if s in received_subscription_eosenotices:
                    my_event = received_subscription_eosenotices[s]
                    s_original = s[len(f"{self.subscription_id_rewrite}_") :]
                    event_to_forward = ["EOSE", s_original]
                    del received_subscription_eosenotices[s]
                    # send data back to client
                    await self.websocket.send_text(json.dumps(event_to_forward))
            await asyncio.sleep(0.1)

    async def start(self):
        self.tasks.append(asyncio.create_task(self.client_to_nostr()))
        self.tasks.append(asyncio.create_task(self.nostr_to_client()))

    async def stop(self):
        for t in self.tasks:
            t.cancel()

    def _marshall_nostr_filters(self, data: Union[dict, list]):
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

    async def _add_nostr_subscription(self, json_str):
        """Parses a (string) request from a client. If it is a subscription (REQ), it will
        register the subscription in the nostr client library that we're using so we can
        receive the callbacks on it later. Will rewrite the subscription id since we expect
        multiple clients to use the router and want to avoid subscription id collisions"""
        json_data = json.loads(json_str)
        assert len(json_data)
        if json_data[0] == "REQ":
            subscription_id = json_data[1]
            subscription_id_rewritten = (
                f"{self.subscription_id_rewrite}_{subscription_id}"
            )
            fltr = json_data[2]
            filters = self._marshall_nostr_filters(fltr)
            client.relay_manager.add_subscription(subscription_id_rewritten, filters)
            request_rewritten = json.dumps(["REQ", subscription_id_rewritten, fltr])
            return subscription_id_rewritten, request_rewritten
        return None, None
