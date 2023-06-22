import asyncio
import threading

from .crud import get_relays
from .nostr.message_pool import EndOfStoredEventsMessage, EventMessage, NoticeMessage
from .services import (
    nostr,
    received_subscription_eosenotices,
    received_subscription_events,
    received_subscription_notices,
)


async def init_relays():
    # reinitialize the entire client
    nostr.__init__()
    # get relays from db
    relays = await get_relays()
    # set relays and connect to them
    nostr.client.relays = list(set([r.url for r in relays.__root__ if r.url]))
    await nostr.client.connect()


async def subscribe_events():
    while not any([r.connected for r in nostr.client.relay_manager.relays.values()]):
        await asyncio.sleep(2)

    def callback_events(eventMessage: EventMessage):
        if eventMessage.subscription_id in received_subscription_events:
            # do not add duplicate events (by event id)
            if eventMessage.event.id in set(
                [
                    e.id
                    for e in received_subscription_events[eventMessage.subscription_id]
                ]
            ):
                return

            received_subscription_events[eventMessage.subscription_id].append(
                eventMessage.event
            )
        else:
            received_subscription_events[eventMessage.subscription_id] = [
                eventMessage.event
            ]
        return

    def callback_notices(noticeMessage: NoticeMessage):
        if noticeMessage not in received_subscription_notices:
            received_subscription_notices.append(noticeMessage)
        return

    def callback_eose_notices(eventMessage: EndOfStoredEventsMessage):
        if eventMessage.subscription_id not in received_subscription_eosenotices:
            received_subscription_eosenotices[
                eventMessage.subscription_id
            ] = eventMessage

        return

    t = threading.Thread(
        target=nostr.client.subscribe,
        args=(
            callback_events,
            callback_notices,
            callback_eose_notices,
        ),
        name="Nostr-event-subscription",
        daemon=True,
    )
    t.start()
