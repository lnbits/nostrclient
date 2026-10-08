import asyncio
import json

from ..nostr.message_pool import (
    EndOfStoredEventsMessage,
    EventMessage,
    MessagePool,
)
from ..router import NostrRouter, nostr_client
from ..tasks import on_eose_notice, on_event


def _event(subscription_id: str, event_id: str) -> str:
    return json.dumps(["EVENT", subscription_id, {"id": event_id, "content": ""}])


def _eose(subscription_id: str) -> str:
    return json.dumps(["EOSE", subscription_id])


def _drain_events(pool: MessagePool) -> list[EventMessage]:
    events = []
    while pool.has_events():
        events.append(pool.get_event())
    return events


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self, reason: str = "") -> None:
        pass


def test_pool_accepts_and_deduplicates_open_subscription_events():
    pool = MessagePool()
    pool.open_subscription("sub")

    pool.add_message(_event("sub", "a"), "wss://one")
    pool.add_message(_event("sub", "a"), "wss://two")
    pool.add_message(_event("sub", "b"), "wss://one")
    pool.add_message(_eose("sub"), "wss://one")

    assert [e.event_id for e in _drain_events(pool)] == ["a", "b"]
    assert pool.has_eose_notices()


def test_pool_drops_messages_for_unknown_subscriptions():
    pool = MessagePool()

    pool.add_message(_event("unknown", "a"), "wss://one")
    pool.add_message(_eose("unknown"), "wss://one")

    assert not pool.has_events()
    assert not pool.has_eose_notices()
    assert pool.tracked_event_count() == 0


def test_pool_forgets_closed_subscription_state_and_late_messages():
    pool = MessagePool()
    pool.open_subscription("sub")
    pool.add_message(_event("sub", "a"), "wss://one")
    _drain_events(pool)
    assert pool.tracked_event_count() == 1

    pool.close_subscription("sub")
    pool.add_message(_event("sub", "late"), "wss://one")
    pool.add_message(_eose("sub"), "wss://one")

    assert pool.tracked_event_count() == 0
    assert not pool.is_subscription_open("sub")
    assert not pool.has_events()
    assert not pool.has_eose_notices()


def test_pool_tracking_is_bounded_by_open_subscriptions():
    pool = MessagePool()
    for index in range(100):
        subscription_id = f"sub-{index}"
        pool.open_subscription(subscription_id)
        pool.add_message(_event(subscription_id, "a"), "wss://one")
        pool.close_subscription(subscription_id)

    assert pool.tracked_event_count() == 0


def test_relay_manager_opens_and_closes_pool_subscription():
    manager = nostr_client.relay_manager
    pool = manager.message_pool

    manager.add_subscription("manager-sub", [{"kinds": [1]}])
    assert pool.is_subscription_open("manager-sub")

    manager.close_subscription("manager-sub")
    assert not pool.is_subscription_open("manager-sub")


def test_queued_messages_for_closed_subscription_are_not_cached():
    pool = nostr_client.relay_manager.message_pool
    pool.open_subscription("queued")
    pool.close_subscription("queued")

    on_event(EventMessage("{}", "a", "queued", "wss://one"))
    on_eose_notice(EndOfStoredEventsMessage("queued", "wss://one"))

    assert "queued" not in NostrRouter.received_subscription_events
    assert "queued" not in NostrRouter.received_subscription_eosenotices


def test_router_close_forgets_cached_messages():
    router = NostrRouter(FakeWebSocket())  # type: ignore[arg-type]
    router._handle_client_req(["REQ", "client-sub", {"kinds": [1]}])
    (subscription_id,) = router.subscriptions
    on_event(EventMessage("{}", "a", subscription_id, "wss://one"))
    on_eose_notice(EndOfStoredEventsMessage(subscription_id, "wss://one"))

    router._handle_client_close("client-sub")

    assert subscription_id not in NostrRouter.received_subscription_events
    assert subscription_id not in NostrRouter.received_subscription_eosenotices
    assert not nostr_client.relay_manager.message_pool.is_subscription_open(
        subscription_id
    )


def test_router_stop_forgets_cached_messages():
    router = NostrRouter(FakeWebSocket())  # type: ignore[arg-type]
    router._handle_client_req(["REQ", "client-sub", {"kinds": [1]}])
    (subscription_id,) = router.subscriptions
    on_event(EventMessage("{}", "a", subscription_id, "wss://one"))
    on_eose_notice(EndOfStoredEventsMessage(subscription_id, "wss://one"))

    asyncio.run(router.stop())

    assert subscription_id not in NostrRouter.received_subscription_events
    assert subscription_id not in NostrRouter.received_subscription_eosenotices
    assert not nostr_client.relay_manager.message_pool.is_subscription_open(
        subscription_id
    )
