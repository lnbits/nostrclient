from typing import List, Optional, Union

from lnbits.helpers import urlsafe_short_hash
import shortuuid
from . import db
from .models import Relay, RelayList


async def get_relays() -> RelayList:
    row = await db.fetchall("SELECT * FROM nostradmin.relays")
    return RelayList(__root__=row)


async def add_relay(relay: Relay) -> None:
    await db.execute(
        f"""
        INSERT INTO nostradmin.relays (
            id,
            url,
            active
        )
        VALUES (?, ?, ?)
        """,
        (relay.id, relay.url, relay.active),
    )


async def delete_relay(relay: Relay) -> None:
    await db.execute("DELETE FROM nostradmin.relays WHERE id = ?", (relay.id,))
