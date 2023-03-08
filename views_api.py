from http import HTTPStatus
import asyncio
import ssl
import json
import datetime
from typing import List, Union
from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.param_functions import Query
from fastapi.params import Depends
from fastapi.responses import JSONResponse

from starlette.exceptions import HTTPException
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from . import nostrclient_ext

from .tasks import client, received_event_queue, received_subscription_events

from .crud import get_relays, add_relay, delete_relay
from .models import RelayList, Relay, Event, Filter, Filters

from .nostr.event import Event as NostrEvent
from .nostr.event import EncryptedDirectMessage
from .nostr.filter import Filter as NostrFilter
from .nostr.filter import Filters as NostrFilters
from .nostr.message_type import ClientMessageType

from lnbits.decorators import (
    WalletTypeInfo,
    get_key_type,
    require_admin_key,
    check_admin,
)

from lnbits.helpers import urlsafe_short_hash
from .tasks import init_relays


@nostrclient_ext.get("/api/v1/relays")
async def api_get_relays():  # type: ignore
    relays = RelayList(__root__=[])
    for url, r in client.relay_manager.relays.items():
        status_text = (
            f"⬆️ {r.num_sent_events} ⬇️ {r.num_received_events} ⚠️ {r.error_counter}"
        )
        connected_text = "🟢" if r.connected else "🔴"
        relay_id = urlsafe_short_hash()
        relays.__root__.append(
            Relay(
                id=relay_id,
                url=url,
                connected_string=connected_text,
                status=status_text,
                ping=r.ping,
                connected=True,
                active=True,
            )
        )
    return relays


@nostrclient_ext.post(
    "/api/v1/relay", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_add_relay(relay: Relay):  # type: ignore
    assert relay.url, "no URL"
    if relay.url in client.relay_manager.relays:
        return
    relay.id = urlsafe_short_hash()
    await add_relay(relay)
    await init_relays()


@nostrclient_ext.delete(
    "/api/v1/relay", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_delete_relay(relay: Relay):  # type: ignore
    assert relay.url
    client.relay_manager.remove_relay(relay.url)
    await delete_relay(relay)


def marshall_nostr_filters(data: Union[dict, list]):
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


async def add_nostr_subscription(json_str):
    """Parses a (string) request from a client. If it is a subscription (REQ), it will
    register the subscription in the nostr client library that we're using so we can
    receive the callbacks on it later"""
    json_data = json.loads(json_str)
    assert len(json_data)
    if json_data[0] == "REQ":
        subscription_id = json_data[1]
        fltr = json_data[2]
        filters = marshall_nostr_filters(fltr)
        client.relay_manager.add_subscription(subscription_id, filters)
        return subscription_id


@nostrclient_ext.websocket("/api/v1/relay")
async def ws_relay(websocket: WebSocket):
    """Relay multiplexer: one client (per endpoint) <-> multiple relays"""
    await websocket.accept()
    my_subscriptions: List[str] = []
    connected: bool = True
    last_sent: datetime.datetime = datetime.datetime.now()

    async def client_to_nostr(websocket):
        """Receives requests / data from the client and forwards it to relays. If the
        request was a subscription/filter, registers it with the nostr client lib.
        Remembers the subscription id so we can send back responses from the relay to this
        client in `nostr_to_client`"""
        nonlocal my_subscriptions
        nonlocal last_sent
        nonlocal connected
        while True:
            try:
                json_str = await websocket.receive_text()
            except WebSocketDisconnect:
                connected = False
                break
            # print(json_str)

            # registers a subscription if the input was a REQ request
            subscription_id = await add_nostr_subscription(json_str)
            if subscription_id:
                my_subscriptions.append(subscription_id)

            # publish data
            client.relay_manager.publish_message(json_str)

            # update timestamp of last sent data
            last_sent = datetime.datetime.now()

    async def nostr_to_client(websocket):
        """Sends responses from relays back to the client. Polls the subscriptions of this client
        stored in `my_subscriptions`. Then gets all responses for this subscription id from `received_subscription_events` which
        is filled in tasks.py. Takes one response after the other and relays it back to the client. Reconstructs
        the reponse manually because the nostr client lib we're using can't do it."""
        nonlocal connected
        while True and connected:
            for s in my_subscriptions:
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
                        event_to_forward = ["EVENT", s, event_json]
                        # print(json.dumps(event_to_forward))

                        # send data back to client
                        await websocket.send_text(json.dumps(event_to_forward))
            await asyncio.sleep(0.1)

    asyncio.create_task(client_to_nostr(websocket))
    asyncio.create_task(nostr_to_client(websocket))

    # we kill this websocket and the subscriptions if no data was sent for
    # more than 10 minutes _or_ if the user disconnects and thus `connected==False`
    while True:
        await asyncio.sleep(10)
        if (
            datetime.datetime.now() - last_sent > datetime.timedelta(minutes=10)
            or not connected
        ):
            break
