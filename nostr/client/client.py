import asyncio
from typing import List

from ..relay_manager import RelayManager


class NostrClient:
    relays = [ ]
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

    async def subscribe(
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

            await asyncio.sleep(0.5)
