import asyncio
import ssl
import json
import threading

from .crud import get_relays
from .nostr.event import Event
from .nostr.key import PublicKey
from .nostr.message_pool import EndOfStoredEventsMessage, EventMessage, NoticeMessage
from .nostr.relay_manager import RelayManager
from .services import (
    nostr,
    received_subscription_eosenotices,
    received_subscription_events,
)


async def init_relays():
    # we save any subscriptions teporarily to re-add them after reinitializing the client
    subscriptions = {}
    for relay in nostr.client.relay_manager.relays.values():
        # relay.add_subscription(id, filters)
        for subscription_id, filters in relay.subscriptions.items():
            subscriptions[subscription_id] = filters

    # reinitialize the entire client
    nostr.__init__()
    # get relays from db
    relays = await get_relays()
    # set relays and connect to them
    nostr.client.relays = list(set([r.url for r in relays.__root__ if r.url]))
    nostr.client.connect()

    await asyncio.sleep(2)
    # re-add subscriptions
    for subscription_id, subscription in subscriptions.items():
        nostr.client.relay_manager.add_subscription(
            subscription_id, subscription.filters
        )
        s = subscription.to_json_object()
        json_str = json.dumps(["REQ", s["id"], s["filters"][0]])
        nostr.client.relay_manager.publish_message(json_str)
    return


async def subscribe_events():
    while not any([r.connected for r in nostr.client.relay_manager.relays.values()]):
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
