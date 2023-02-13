import asyncio
import ssl
import threading

from .nostr.client.client import NostrClient
from .nostr.event import Event
from .nostr.key import PublicKey
from .nostr.relay_manager import RelayManager

# relays = [
#     "wss://nostr.mom",
#     "wss://nostr-pub.wellorder.net",
#     "wss://nostr.zebedee.cloud",
#     "wss://relay.damus.io",
#     "wss://relay.nostr.info",
#     "wss://nostr.onsats.org",
#     "wss://nostr-relay.untethr.me",
#     "wss://relay.snort.social",
#     "wss://lnbits.link/nostrrelay/client",
# ]
client = NostrClient(
    connect=False,
)

# client = NostrClient(
#     connect=False,
#     privatekey_hex="211aac75a687ad96cca402406f8147a2726e31c5fc838e22ce30640ca1f3a6fe",
# )

received_event_queue: asyncio.Queue[Event] = asyncio.Queue(0)

from .crud import get_relays


async def init_relays():
    relays = await get_relays()
    client.relays = [r.url for r in relays.__root__]
    client.connect()
    return


# async def send_data():
#     while not any([r.connected for r in client.relay_manager.relays.values()]):
#         print("no relays connected yet")
#         await asyncio.sleep(0.5)
#     while True:
#         client.dm("test", PublicKey(bytes.fromhex(client.public_key.hex())))
#         print("sent DM")
#         await asyncio.sleep(5)
#     return


# async def receive_data():
#     while not any([r.connected for r in client.relay_manager.relays.values()]):
#         print("no relays connected yet")
#         await asyncio.sleep(0.5)

#     def callback(event: Event, decrypted_content=None):
#         print(
#             f"From {event.public_key[:3]}..{event.public_key[-3:]}: {decrypted_content or event.content}"
#         )

#     t = threading.Thread(
#         target=client.get_dm,
#         args=(
#             client.public_key,
#             callback,
#         ),
#         name="Nostr DM",
#     )
#     t.start()


async def subscribe_events():
    while not any([r.connected for r in client.relay_manager.relays.values()]):
        print("no relays connected yet")
        await asyncio.sleep(1)

    def callback(event: Event):
        print(f"From {event.public_key[:3]}..{event.public_key[-3:]}: {event.content}")
        asyncio.run(received_event_queue.put(event))

    t = threading.Thread(
        target=client.subscribe,
        args=(callback,),
        name="Nostr-event-subscription",
    )
    t.start()
