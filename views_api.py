import asyncio
from http import HTTPStatus
from typing import List

from fastapi import Depends, WebSocket
from loguru import logger
from starlette.exceptions import HTTPException

from lnbits.decorators import check_admin
from lnbits.helpers import urlsafe_short_hash

from . import nostr_client, nostrclient_ext, scheduled_tasks
from .crud import add_relay, delete_relay, get_relays
from .helpers import normalize_public_key
from .models import Relay, TestMessage, TestMessageResponse
from .nostr.key import EncryptedDirectMessage, PrivateKey
from .router import NostrRouter

# we keep this in
all_routers: list[NostrRouter] = []


@nostrclient_ext.get("/api/v1/relays")
async def api_get_relays() -> List[Relay]:
    relays = []
    for url, r in nostr_client.relay_manager.relays.items():
        relay_id = urlsafe_short_hash()
        relays.append(
            Relay(
                id=relay_id,
                url=url,
                connected=r.connected,
                status={
                    "num_sent_events": r.num_sent_events,
                    "num_received_events": r.num_received_events,
                    "error_counter": r.error_counter,
                    "error_list": r.error_list,
                    "notice_list": r.notice_list,
                },
                ping=r.ping,
                active=True,
            )
        )
    return relays


@nostrclient_ext.post(
    "/api/v1/relay", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_add_relay(relay: Relay) -> List[Relay]:
    if not relay.url:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Relay url not provided."
        )
    if relay.url in nostr_client.relay_manager.relays:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Relay: {relay.url} already exists.",
        )
    relay.id = urlsafe_short_hash()
    await add_relay(relay)

    nostr_client.relay_manager.add_relay(relay.url)

    return await get_relays()


@nostrclient_ext.delete(
    "/api/v1/relay", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_delete_relay(relay: Relay) -> None:
    if not relay.url:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Relay url not provided."
        )
    # we can remove relays during runtime
    nostr_client.relay_manager.remove_relay(relay.url)
    await delete_relay(relay)


@nostrclient_ext.put(
    "/api/v1/relay/test", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_test_endpoint(data: TestMessage) -> TestMessageResponse:
    try:
        to_public_key = normalize_public_key(data.reciever_public_key)

        pk = bytes.fromhex(data.sender_private_key) if data.sender_private_key else None
        private_key = PrivateKey(pk) if pk else PrivateKey()

        dm = EncryptedDirectMessage(
            recipient_pubkey=to_public_key, cleartext_content=data.message
        )
        private_key.sign_event(dm)

        return TestMessageResponse(
            private_key=private_key.hex(),
            public_key=to_public_key,
            event_json=dm.to_message(),
        )
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
            router.stop()
            all_routers.remove(router)
        except Exception as e:
            logger.error(e)

    nostr_client.close()

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
    router.start()
    all_routers.append(router)

    # we kill this websocket and the subscriptions
    # if the user disconnects and thus `connected==False`
    while True:
        await asyncio.sleep(10)
        if not router.connected:
            router.stop()
            all_routers.remove(router)
            break
