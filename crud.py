import json
from typing import Optional

from lnbits.db import Database

from .models import Config, Relay

db = Database("ext_nostrclient")


async def get_relays() -> list[Relay]:
    return await db.fetchall(
        "SELECT * FROM nostrclient.relays",
        model=Relay,
    )


async def add_relay(relay: Relay) -> Relay:
    await db.insert("nostrclient.relays", relay)
    return relay


async def delete_relay(relay: Relay) -> None:
    if not relay.url:
        return
    await db.execute(
        "DELETE FROM nostrclient.relays WHERE url = :url", {"url": relay.url}
    )


######################CONFIG#######################
async def create_config() -> Config:
    config = Config()
    await db.execute(
        """
        INSERT INTO nostrclient.config (json_data)
        VALUES (?)
        """,
        (json.dumps(config.dict()),),
    )
    row = await db.fetchone("SELECT json_data FROM nostrclient.config", ())
    return json.loads(row[0], object_hook=lambda d: Config(**d))


async def update_config(config: Config) -> Optional[Config]:
    await db.execute(
        """UPDATE nostrclient.config SET json_data = ?""",
        (json.dumps(config.dict()),),
    )
    row = await db.fetchone("SELECT json_data FROM nostrclient.config", ())
    return json.loads(row[0], object_hook=lambda d: Config(**d))


async def get_config() -> Optional[Config]:
    row = await db.fetchone("SELECT json_data FROM nostrclient.config", ())
    return json.loads(row[0], object_hook=lambda d: Config(**d)) if row else None
