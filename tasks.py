import asyncio
import threading

from loguru import logger

from .crud import get_relays
from .nostr.message_pool import EndOfStoredEventsMessage, EventMessage, NoticeMessage
from .router import NostrRouter, nostr_client


async def init_relays():
    # get relays from db
    relays = await get_relays()
    # set relays and connect to them
    valid_relays = [r.url for r in relays if r.url]

    nostr_client.reconnect(valid_relays)


async def check_relays():
    """Check relays that have been disconnected"""
    while True:
        try:
            await asyncio.sleep(20)
            nostr_client.relay_manager.check_and_restart_relays()
        except Exception as e:
            logger.warning(f"Cannot restart relays: '{e!s}'.")


async def subscribe_events():
    while not [r.connected for r in nostr_client.relay_manager.relays.values()]:
        await asyncio.sleep(2)

    def callback_events(event_message: EventMessage):
        sub_id = event_message.subscription_id
        if sub_id not in NostrRouter.received_subscription_events:
            NostrRouter.received_subscription_events[sub_id] = [event_message]
            return

        # do not add duplicate events (by event id)
        ids = [e.event_id for e in NostrRouter.received_subscription_events[sub_id]]
        if event_message.event_id in ids:
            return

        NostrRouter.received_subscription_events[sub_id].append(event_message)

    def callback_notices(notice_message: NoticeMessage):
        if notice_message not in NostrRouter.received_subscription_notices:
            NostrRouter.received_subscription_notices.append(notice_message)

    def callback_eose_notices(event_message: EndOfStoredEventsMessage):
        sub_id = event_message.subscription_id
        if sub_id in NostrRouter.received_subscription_eosenotices:
            return

        NostrRouter.received_subscription_eosenotices[sub_id] = event_message

    def wrap_async_subscribe():
        asyncio.run(
            nostr_client.subscribe(
                callback_events,
                callback_notices,
                callback_eose_notices,
            )
        )

    t = threading.Thread(
        target=wrap_async_subscribe,
        name="Nostr-event-subscription",
        daemon=True,
    )
    t.start()
