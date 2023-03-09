import asyncio
import ssl
import threading

from .nostr.client.client import NostrClient
from .nostr.event import Event
from .nostr.message_pool import EventMessage, NoticeMessage, EndOfStoredEventsMessage
from .nostr.key import PublicKey
from .nostr.relay_manager import RelayManager


client = NostrClient(
    connect=False,
)

received_event_queue: asyncio.Queue[EventMessage] = asyncio.Queue(0)
received_subscription_events: dict[str, list[Event]] = {}
received_subscription_notices: dict[str, list[NoticeMessage]] = {}
received_subscription_eosenotices: dict[str, EndOfStoredEventsMessage] = {}

from .crud import get_relays


async def init_relays():
    relays = await get_relays()
    client.relays = list(set([r.url for r in relays.__root__ if r.url]))
    client.connect()
    return


async def subscribe_events():
    while not any([r.connected for r in client.relay_manager.relays.values()]):
        await asyncio.sleep(2)

    def callback_events(eventMessage: EventMessage):
        # print(f"From {event.public_key[:3]}..{event.public_key[-3:]}: {event.content}")
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

    def callback_notices(eventMessage: NoticeMessage):
        return

    def callback_eose_notices(eventMessage: EndOfStoredEventsMessage):
        if eventMessage.subscription_id not in received_subscription_eosenotices:
            received_subscription_eosenotices[
                eventMessage.subscription_id
            ] = eventMessage

        return

    t = threading.Thread(
        target=client.subscribe,
        args=(
            callback_events,
            callback_notices,
            callback_eose_notices,
        ),
        name="Nostr-event-subscription",
        daemon=True,
    )
    t.start()
