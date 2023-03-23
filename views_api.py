import asyncio
from http import HTTPStatus
from typing import Optional

from fastapi import Depends, WebSocket
from loguru import logger
from starlette.exceptions import HTTPException

from lnbits.decorators import check_admin
from lnbits.helpers import urlsafe_short_hash

from . import nostrclient_ext
from .crud import add_relay, delete_relay, get_relays
from .models import Relay, RelayList
from .services import NostrRouter, nostr
from .tasks import init_relays

# we keep this in
all_routers: list[NostrRouter] = []


@nostrclient_ext.get("/api/v1/relays")
async def api_get_relays() -> RelayList:
    relays = RelayList(__root__=[])
    for url, r in nostr.client.relay_manager.relays.items():
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
async def api_add_relay(relay: Relay) -> Optional[RelayList]:
    if not relay.url:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=f"Relay url not provided."
        )
    if relay.url in nostr.client.relay_manager.relays:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Relay: {relay.url} already exists.",
        )
    relay.id = urlsafe_short_hash()
    await add_relay(relay)
    # we can't add relays during runtime yet
    await init_relays()
    return await get_relays()


@nostrclient_ext.delete(
    "/api/v1/relay", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_delete_relay(relay: Relay) -> None:
    if not relay.url:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=f"Relay url not provided."
        )
    # we can remove relays during runtime
    nostr.client.relay_manager.remove_relay(relay.url)
    await delete_relay(relay)


@nostrclient_ext.delete(
    "/api/v1", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_stop():
    for router in all_routers:
        try:
            for s in router.subscriptions:
                nostr.client.relay_manager.close_subscription(s)
            await router.stop()
            all_routers.remove(router)
        except Exception as e:
            logger.error(e)
    try:
        nostr.client.relay_manager.close_connections()
    except Exception as e:
        logger.error(e)

    return {"success": True}


@nostrclient_ext.websocket("/api/v1/relay")
async def ws_relay(websocket: WebSocket) -> None:
    """Relay multiplexer: one client (per endpoint) <-> multiple relays"""
    await websocket.accept()
    router = NostrRouter(websocket)
    await router.start()
    all_routers.append(router)

    # we kill this websocket and the subscriptions if the user disconnects and thus `connected==False`
    while True:
        await asyncio.sleep(10)
        if not router.connected:
            for s in router.subscriptions:
                try:
                    nostr.client.relay_manager.close_subscription(s)
                except:
                    pass
            await router.stop()
            all_routers.remove(router)
            break
