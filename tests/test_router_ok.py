import json
import time

import pytest

from .. import router as router_module
from ..nostr.message_pool import CommandResultMessage
from ..router import PUBLISH_TIMEOUT_SECONDS, NostrRouter


class FakeWebSocket:
    def __init__(self):
        self.sent: list[list] = []

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))


class FakeRelay:
    def __init__(self, connected: bool):
        self.connected = connected


class FakeRelayManager:
    def __init__(self, relays: dict[str, FakeRelay]):
        self.relays = relays
        self.published: list[str] = []
        self.subscriptions: list[str] = []

    def publish_message(self, message: str):
        self.published.append(message)

    def add_subscription(self, subscription_id: str, filters):
        self.subscriptions.append(subscription_id)

    def close_subscriptions(self, subscriptions):
        pass


EVENT_ID = "ab" * 32
EVENT_MSG = json.dumps(["EVENT", {"id": EVENT_ID, "kind": 1, "content": "hi"}])


def _router(monkeypatch, relays: dict[str, FakeRelay]):
    manager = FakeRelayManager(relays)
    monkeypatch.setattr(router_module.nostr_client, "relay_manager", manager)
    NostrRouter.received_command_results.clear()
    ws = FakeWebSocket()
    return NostrRouter(ws), ws, manager  # type: ignore[arg-type]


def _ok_from(url: str, accepted: bool, message: str = ""):
    NostrRouter.received_command_results.setdefault(EVENT_ID, []).append(
        CommandResultMessage(EVENT_ID, accepted, message, url)
    )


@pytest.mark.asyncio
async def test_no_connected_relays_replies_ok_false_immediately(monkeypatch):
    router, ws, manager = _router(monkeypatch, {"wss://a": FakeRelay(False)})

    await router._handle_client_to_nostr(EVENT_MSG)

    assert manager.published == []
    assert ws.sent == [["OK", EVENT_ID, False, "error: no relays connected"]]
    assert router.pending_publishes == {}


@pytest.mark.asyncio
async def test_event_without_id_is_ignored(monkeypatch):
    router, ws, manager = _router(monkeypatch, {"wss://a": FakeRelay(True)})

    await router._handle_client_to_nostr(json.dumps(["EVENT", {"kind": 1}]))

    assert manager.published == []
    assert ws.sent == []


@pytest.mark.asyncio
async def test_any_accepting_relay_yields_ok_true(monkeypatch):
    relays = {"wss://a": FakeRelay(True), "wss://b": FakeRelay(True)}
    router, ws, manager = _router(monkeypatch, relays)

    await router._handle_client_to_nostr(EVENT_MSG)
    assert manager.published == [EVENT_MSG]
    assert EVENT_ID in router.pending_publishes

    # nothing answered yet: no OK
    await router._handle_command_results()
    assert ws.sent == []

    _ok_from("wss://a", False, "blocked: kind not allowed")
    await router._handle_command_results()
    assert ws.sent == []  # one rejection out of two relays: keep waiting

    _ok_from("wss://b", True, "")
    await router._handle_command_results()
    assert ws.sent == [["OK", EVENT_ID, True, ""]]
    assert router.pending_publishes == {}
    assert EVENT_ID not in NostrRouter.received_command_results

    # a late OK must not produce a second reply
    _ok_from("wss://a", True, "")
    await router._handle_command_results()
    assert len(ws.sent) == 1


@pytest.mark.asyncio
async def test_all_relays_rejecting_yields_ok_false(monkeypatch):
    relays = {"wss://a": FakeRelay(True), "wss://b": FakeRelay(True)}
    router, ws, _ = _router(monkeypatch, relays)

    await router._handle_client_to_nostr(EVENT_MSG)
    _ok_from("wss://a", False, "invalid: bad sig")
    _ok_from("wss://b", False, "blocked: kind not allowed")
    await router._handle_command_results()

    assert ws.sent == [["OK", EVENT_ID, False, "blocked: kind not allowed"]]
    assert router.pending_publishes == {}


@pytest.mark.asyncio
async def test_timeout_yields_ok_false(monkeypatch):
    router, ws, _ = _router(monkeypatch, {"wss://a": FakeRelay(True)})

    await router._handle_client_to_nostr(EVENT_MSG)
    router.pending_publishes[EVENT_ID].sent_at = (
        time.time() - PUBLISH_TIMEOUT_SECONDS - 1
    )
    await router._handle_command_results()

    assert ws.sent == [["OK", EVENT_ID, False, "error: timed out waiting for relays"]]
    assert router.pending_publishes == {}


@pytest.mark.asyncio
async def test_stop_drops_pending_publishes(monkeypatch):
    router, _, _ = _router(monkeypatch, {"wss://a": FakeRelay(True)})

    await router._handle_client_to_nostr(EVENT_MSG)
    _ok_from("wss://a", True)
    await router.stop()

    assert router.pending_publishes == {}
    assert NostrRouter.received_command_results == {}


@pytest.mark.asyncio
async def test_req_without_configured_relays_is_closed(monkeypatch):
    router, ws, manager = _router(monkeypatch, {})

    await router._handle_client_to_nostr(json.dumps(["REQ", "sub1", {"kinds": [1]}]))

    assert ws.sent == [["CLOSED", "sub1", "error: no relay connections"]]
    assert router.subscriptions == []
    assert manager.subscriptions == []


@pytest.mark.asyncio
async def test_req_with_configured_but_disconnected_relay_is_kept(monkeypatch):
    router, ws, manager = _router(monkeypatch, {"wss://a": FakeRelay(False)})

    await router._handle_client_to_nostr(json.dumps(["REQ", "sub1", {"kinds": [1]}]))

    assert ws.sent == []
    assert len(router.subscriptions) == 1
    assert len(manager.subscriptions) == 1
