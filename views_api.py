import asyncio
from http import HTTPStatus
from typing import List, Optional

from fastapi import Depends, WebSocket
from loguru import logger
from starlette.exceptions import HTTPException

from lnbits.decorators import check_admin
from lnbits.helpers import urlsafe_short_hash

from . import nostrclient_ext, scheduled_tasks
from .crud import add_relay, delete_relay, get_relays
from .helpers import normalize_public_key
from .models import Relay, RelayList, TestMessage, TestMessageResponse
from .nostr.key import EncryptedDirectMessage, PrivateKey
from .nostr.relay import Relay as NostrRelay
from .services import NostrRouter, nostr

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

    all_relays: List[NostrRelay] = nostr.client.relay_manager.relays.values()
    if len(all_relays):
        subscriptions = all_relays[0].subscriptions
        nostr.client.relays.append(relay.url)
        nostr.client.relay_manager.add_relay(subscriptions)
       
        nostr.client.relay_manager.connect_relay(relay.url)

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


@nostrclient_ext.put(
    "/api/v1/relay/test", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_test_endpoint(data: TestMessage) -> TestMessageResponse:
    try:
        to_public_key = normalize_public_key(data.reciever_public_key)

        pk = bytes.fromhex(data.sender_private_key) if data.sender_private_key else None
        private_key = PrivateKey(pk)

        dm = EncryptedDirectMessage(
            recipient_pubkey=to_public_key, cleartext_content=data.message
        )
        private_key.sign_event(dm)

        return TestMessageResponse(private_key=private_key.hex(), public_key=to_public_key, event_json=dm.to_message())
    except (ValueError, AssertionError) as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=str(ex),
        )
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot generate test event",
        )



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

    for scheduled_task in scheduled_tasks:
        try:
            scheduled_task.cancel()
        except Exception as ex:
            logger.warning(ex)

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
