import pytest
from nostr_sdk import EventId, RelayMessage, RelayUrl

from ..nostr.message_pool import MessagePool
from ..nostr.relay_manager import RelayConnection, _NotificationHandler

EVENT_ID = "ab" * 32


class FakeRelayManager:
    def __init__(self):
        self.message_pool = MessagePool()
        self.relay = RelayConnection("wss://relay.example")

    def _ensure_relay_state(self, url):
        return self.relay

    async def _get_sdk_relay(self, url):
        return None


@pytest.mark.asyncio
async def test_ok_messages_reach_the_pool():
    manager = FakeRelayManager()
    handler = _NotificationHandler(manager)  # type: ignore[arg-type]

    await handler.handle_msg(
        RelayUrl.parse("wss://relay.example"),
        RelayMessage.ok(EventId.parse(EVENT_ID), False, "blocked: not allowed"),
    )

    assert manager.message_pool.has_command_results()
    result = manager.message_pool.get_command_result()
    assert (result.event_id, result.accepted, result.message, result.url) == (
        EVENT_ID,
        False,
        "blocked: not allowed",
        "wss://relay.example",
    )
