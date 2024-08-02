import json
from typing import Optional

from lnbits.db import Database

from .models import Config, Relay

db = Database("ext_nostrclient")


async def get_relays() -> list[Relay]:
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


######################CONFIG#######################
async def create_config() -> Config:
    config = Config()
    await db.execute(
        """
        INSERT INTO nostrclient.config (json_data)
        VALUES (?)
        """,
        (json.dumps(config.dict())),
    )
    row = await db.fetchone("SELECT json_data FROM nostrclient.config", ())
    return json.loads(row[0], object_hook=lambda d: Config(**d))


async def update_config(config: Config) -> Optional[Config]:
    await db.execute(
        """UPDATE nostrclient.config SET json_data = ?""",
        (json.dumps(config.dict())),
    )
    row = await db.fetchone("SELECT json_data FROM nostrclient.config", ())
    return json.loads(row[0], object_hook=lambda d: Config(**d))


async def get_config() -> Optional[Config]:
    row = await db.fetchone("SELECT json_data FROM nostrclient.config", ())
    return json.loads(row[0], object_hook=lambda d: Config(**d)) if row else None
