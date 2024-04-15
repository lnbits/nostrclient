import asyncio
from http import HTTPStatus
from typing import List

from fastapi import Depends, WebSocket
from loguru import logger
from starlette.exceptions import HTTPException

from lnbits.decorators import check_admin
from lnbits.helpers import decrypt_internal_message, urlsafe_short_hash

from . import all_routers, nostr_client, nostrclient_ext
from .crud import add_relay, create_config, delete_relay, get_config, get_relays, update_config
from .helpers import normalize_public_key
from .models import Config, Relay, TestMessage, TestMessageResponse
from .nostr.key import EncryptedDirectMessage, PrivateKey
from .router import NostrRouter


@nostrclient_ext.get("/api/v1/relays",  dependencies=[Depends(check_admin)])
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


@nostrclient_ext.websocket("/api/v1/{id}")
async def ws_relay(id: str, websocket: WebSocket) -> None:
    """Relay multiplexer: one client (per endpoint) <-> multiple relays"""

    logger.info("New websocket connection at: '/api/v1/relay'")
    try:
        config = await get_config()

        if not config.private_ws and not config.public_ws:
            raise ValueError("Websocket connections not accepted.")

        if id == "relay":
            if not config.public_ws:
                raise ValueError("Public websocket connections not accepted.")
        else:
            if not config.private_ws:
                raise ValueError("Private websocket connections not accepted.")
            if decrypt_internal_message(id) != "relay":
                raise ValueError("Invalid websocket endpoint.")


        await websocket.accept()
        router = NostrRouter(websocket)
        router.start()
        all_routers.append(router)

        # we kill this websocket and the subscriptions
        # if the user disconnects and thus `connected==False`
        while router.connected:
            await asyncio.sleep(10)

        try:
            await router.stop()
        except Exception as e:
            logger.debug(e)

        all_routers.remove(router)
        logger.info("Closed websocket connection at: '/api/v1/relay'")
    except ValueError as ex:
        logger.warning(ex)
        await websocket.close(reason=str(ex))
    except Exception as ex:
        logger.warning(ex)
        await websocket.close(reason="Websocket connection unexpected closed")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot accept websocket connection",
        )


@nostrclient_ext.get("/api/v1/config",  dependencies=[Depends(check_admin)])
async def api_get_relays() -> Config:
    config = await get_config()
    if not config:
        await create_config()

    return config

@nostrclient_ext.put("/api/v1/config", dependencies=[Depends(check_admin)])
async def api_update_config(
    data: Config
):
    config = await update_config(data)
    assert config
    return config.dict()
