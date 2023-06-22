import time
from typing import *

from ..relay_manager import RelayManager
from ..subscription import Subscription


class NostrClient:
    relays = [
        "wss://nostr-pub.wellorder.net",
        "wss://nostr.zebedee.cloud",
        "wss://nodestr.fmt.wiz.biz",
        "wss://nostr.oxtr.dev",
    ]
    relay_manager = RelayManager()

    def __init__(self, relays: List[str] = [], connect=True):
        if len(relays):
            self.relays = relays
        if connect:
            self.connect()

    async def connect(self):
        for relay in self.relays:
            self.relay_manager.add_relay(relay)



    def close(self):
        self.relay_manager.close_connections()

    def subscribe(
        self,
        callback_events_func=None,
        callback_notices_func=None,
        callback_eosenotices_func=None,
    ):
        while True:
            while self.relay_manager.message_pool.has_events():
                event_msg = self.relay_manager.message_pool.get_event()
                if callback_events_func:
                    callback_events_func(event_msg)
            while self.relay_manager.message_pool.has_notices():
                event_msg = self.relay_manager.message_pool.get_notice()
                if callback_notices_func:
                    callback_notices_func(event_msg)
            while self.relay_manager.message_pool.has_eose_notices():
                event_msg = self.relay_manager.message_pool.get_eose_notice()
                if callback_eosenotices_func:
                    callback_eosenotices_func(event_msg)

            time.sleep(0.1)
