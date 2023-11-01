from typing import List

from . import db
from .models import Relay


async def get_relays() -> List[Relay]:
    rows = await db.fetchall("SELECT * FROM nostrclient.relays")
    return [Relay.from_row(r) for r in rows]


async def add_relay(relay: Relay) -> None:
    await db.execute(
        """
        INSERT INTO nostrclient.relays (
            id,
            url,
            active
        )
        VALUES (?, ?, ?)
        """,
        (relay.id, relay.url, relay.active),
    )


async def delete_relay(relay: Relay) -> None:
    await db.execute("DELETE FROM nostrclient.relays WHERE url = ?", (relay.url,))
