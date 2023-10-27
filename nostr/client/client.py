import asyncio

from loguru import logger

from ..relay_manager import RelayManager


# todo: why a module
class NostrClient:
    relay_manager = RelayManager()

    def connect(self, relays):
        for relay in relays:
            try:
                self.relay_manager.add_relay(relay)
            except Exception as e:
                logger.debug(e)

    def reconnect(self, relays):
        self.relay_manager.remove_relays()
        self.connect(relays)

    def close(self):
        self.relay_manager.close_connections()

    async def subscribe(
        self,
        callback_events_func=None,
        callback_notices_func=None,
        callback_eosenotices_func=None,
    ):
        while True:
            self._check_events(callback_events_func)
            self._check_notices(callback_notices_func)
            self._check_eos_notices(callback_eosenotices_func)

            await asyncio.sleep(0.5)

    def _check_events(self, callback_events_func = None):
        try:
            while self.relay_manager.message_pool.has_events():
                event_msg = self.relay_manager.message_pool.get_event()
                if callback_events_func:
                    callback_events_func(event_msg)
        except Exception as e:
            logger.debug(e)

    def _check_notices(self, callback_notices_func = None):
        try:
            while self.relay_manager.message_pool.has_notices():
                event_msg = self.relay_manager.message_pool.get_notice()
                if callback_notices_func:
                    callback_notices_func(event_msg)
        except Exception as e:
            logger.debug(e)

    def _check_eos_notices(self, callback_eosenotices_func = None):
        try:
            while self.relay_manager.message_pool.has_eose_notices():
                event_msg = self.relay_manager.message_pool.get_eose_notice()
                if callback_eosenotices_func:
                    callback_eosenotices_func(event_msg)
        except Exception as e:
            logger.debug(e)
