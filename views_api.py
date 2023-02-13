from http import HTTPStatus
import asyncio
import ssl
import json
from fastapi import Request
from fastapi.param_functions import Query
from fastapi.params import Depends
from fastapi.responses import JSONResponse

from starlette.exceptions import HTTPException
from sse_starlette.sse import EventSourceResponse

from . import nostrclient_ext

from .tasks import client, received_event_queue

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


@nostrclient_ext.post("/api/v1/relay")
async def api_add_relay(relay: Relay):  # type: ignore
    assert relay.url, "no URL"
    relay.id = urlsafe_short_hash()
    await add_relay(relay)
    await init_relays()


@nostrclient_ext.delete("/api/v1/relay")
async def api_delete_relay(relay: Relay):  # type: ignore
    await delete_relay(relay)


@nostrclient_ext.post("/api/v1/publish")
async def api_post_event(event: Event):
    nostr_event = NostrEvent(
        content=event.content,
        public_key=event.pubkey,
        created_at=event.created_at,  # type: ignore
        kind=event.kind,
        tags=event.tags or None,  # type: ignore
        signature=event.sig,
    )
    client.relay_manager.publish_event(nostr_event)


@nostrclient_ext.post("/api/v1/filter")
async def api_subscribe(filter: Filter):
    nostr_filter = NostrFilter(
        event_ids=filter.ids,
        kinds=filter.kinds,  # type: ignore
        authors=filter.authors,
        since=filter.since,
        until=filter.until,
        event_refs=filter.e,
        pubkey_refs=filter.p,
        limit=filter.limit,
    )

    filters = NostrFilters([nostr_filter])
    subscription_id = urlsafe_short_hash()
    client.relay_manager.add_subscription(subscription_id, filters)

    request = [ClientMessageType.REQUEST, subscription_id]
    request.extend(filters.to_json_array())
    message = json.dumps(request)
    client.relay_manager.publish_message(message)

    async def event_getter():
        while True:
            event = await received_event_queue.get()
            if filters.match(event):
                yield event.to_message()

    return EventSourceResponse(
        event_getter(),
        ping=20,
        media_type="text/event-stream",
    )
