from . import db
from .models import Relay, RelayList


async def get_relays() -> RelayList:
    row = await db.fetchall("SELECT * FROM nostrclient.relays")
    return RelayList(__root__=row)


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
