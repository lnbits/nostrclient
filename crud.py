from typing import Optional

from lnbits.db import Database

from .models import Config, Relay, UserConfig

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
async def create_config(owner_id: str) -> UserConfig:
    admin_config = UserConfig(owner_id=owner_id)
    await db.insert("nostrclient.config", admin_config)
    return admin_config


async def update_config(owner_id: str, config: Config) -> UserConfig:
    user_config = UserConfig(owner_id=owner_id, extra=config)
    await db.update("nostrclient.config", user_config, "WHERE owner_id = :owner_id")
    return user_config


async def get_config(owner_id: str) -> Optional[UserConfig]:
    return await db.fetchone(
        """
            SELECT * FROM nostrclient.config
            WHERE owner_id = :owner_id
        """,
        {"owner_id": owner_id},
        model=UserConfig,
    )
