import asyncio
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from lnbits.decorators import check_admin
from lnbits.helpers import decrypt_internal_message, urlsafe_short_hash
from loguru import logger

from .crud import (
    add_relay,
    create_config,
    delete_relay,
    get_config,
    get_relays,
    update_config,
)
from .helpers import normalize_public_key
from .models import Config, Relay, RelayStatus, TestMessage, TestMessageResponse
from .nostr.key import EncryptedDirectMessage, PrivateKey
from .router import NostrRouter, all_routers, nostr_client

nostrclient_api_router = APIRouter()


@nostrclient_api_router.get("/api/v1/relays", dependencies=[Depends(check_admin)])
async def api_get_relays() -> list[Relay]:
    relays = []
    for url, r in nostr_client.relay_manager.relays.items():
        relay_id = urlsafe_short_hash()
        relays.append(
            Relay(
                id=relay_id,
                url=url,
                connected=r.connected,
                status=RelayStatus(
                    num_sent_events=r.num_sent_events,
                    num_received_events=r.num_received_events,
                    error_counter=r.error_counter,
                    error_list=r.error_list,
                    notice_list=r.notice_list,
                ),
                ping=r.ping,
                active=True,
            )
        )
    return relays


@nostrclient_api_router.post(
    "/api/v1/relay", status_code=HTTPStatus.OK, dependencies=[Depends(check_admin)]
)
async def api_add_relay(relay: Relay) -> list[Relay]:
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


@nostrclient_api_router.delete(
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


@nostrclient_api_router.put(
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
        ) from ex
    except Exception as ex:
        logger.warning(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Cannot generate test event",
        ) from ex


@nostrclient_api_router.websocket("/api/v1/{ws_id}")
async def ws_relay(ws_id: str, websocket: WebSocket) -> None:
    """Relay multiplexer: one client (per endpoint) <-> multiple relays"""

    logger.info("New websocket connection at: '/api/v1/relay'")
    try:
        config = await get_config(owner_id="admin")
        assert config, "Failed to get config"

        if not config.private_ws and not config.public_ws:
            raise ValueError("Websocket connections not accepted.")

        if ws_id == "relay":
            if not config.public_ws:
                raise ValueError("Public websocket connections not accepted.")
        else:
            if not config.private_ws:
                raise ValueError("Private websocket connections not accepted.")
            if decrypt_internal_message(ws_id, urlsafe=True) != "relay":
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
        ) from ex


@nostrclient_api_router.get("/api/v1/config", dependencies=[Depends(check_admin)])
async def api_get_config() -> Config:
    config = await get_config(owner_id="admin")
    if not config:
        config = await create_config(owner_id="admin")
        assert config, "Failed to create config"
    return config


@nostrclient_api_router.put("/api/v1/config", dependencies=[Depends(check_admin)])
async def api_update_config(data: Config):
    config = await update_config(owner_id="admin", config=data)
    assert config
    return config.dict()
