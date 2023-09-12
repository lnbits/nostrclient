import asyncio
import threading

from loguru import logger

from . import nostr
from .crud import get_relays
from .nostr.message_pool import EndOfStoredEventsMessage, EventMessage, NoticeMessage
from .router import NostrRouter, nostr


async def init_relays():
    # reinitialize the entire client
    nostr.__init__()
    # get relays from db
    relays = await get_relays()
    # set relays and connect to them
    nostr.client.relays = list(set([r.url for r in relays.__root__ if r.url]))
    await nostr.client.connect()


async def check_relays():
    """ Check relays that have been disconnected """
    while True:
        try:
            await asyncio.sleep(20)
            nostr.client.relay_manager.check_and_restart_relays()
        except Exception as e:
            logger.warning(f"Cannot restart relays: '{str(e)}'.")
    

async def subscribe_events():
    while not any([r.connected for r in nostr.client.relay_manager.relays.values()]):
        await asyncio.sleep(2)

    def callback_events(eventMessage: EventMessage):
        if eventMessage.subscription_id in NostrRouter.received_subscription_events:
            # do not add duplicate events (by event id)
            if eventMessage.event.id in set(
                [
                    e.id
                    for e in NostrRouter.received_subscription_events[eventMessage.subscription_id]
                ]
            ):
                return

            NostrRouter.received_subscription_events[eventMessage.subscription_id].append(
                eventMessage.event
            )
        else:
            NostrRouter.received_subscription_events[eventMessage.subscription_id] = [
                eventMessage.event
            ]
        return

    def callback_notices(noticeMessage: NoticeMessage):
        if noticeMessage not in NostrRouter.received_subscription_notices:
            NostrRouter.received_subscription_notices.append(noticeMessage)
        return

    def callback_eose_notices(eventMessage: EndOfStoredEventsMessage):
        if eventMessage.subscription_id not in NostrRouter.received_subscription_eosenotices:
            NostrRouter.received_subscription_eosenotices[
                eventMessage.subscription_id
            ] = eventMessage

        return

    def wrap_async_subscribe():
        asyncio.run(nostr.client.subscribe(
            callback_events,
            callback_notices,
            callback_eose_notices,
        ))

    t = threading.Thread(
        target=wrap_async_subscribe,
        name="Nostr-event-subscription",
        daemon=True,
    )
    t.start()
