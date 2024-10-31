async def m001_initial(db):
    """
    Initial nostrclient table.
    """
    await db.execute(
        """
        CREATE TABLE nostrclient.relays (
            id TEXT NOT NULL PRIMARY KEY,
            url TEXT NOT NULL,
            active BOOLEAN DEFAULT true
        );
    """
    )


async def m002_create_config_table(db):
    """
    Allow the extension to persist and retrieve any number of config values.
    """

    await db.execute(
        """CREATE TABLE nostrclient.config (
            json_data TEXT NOT NULL
        );"""
    )


async def m003_update_config_table(db):
    await db.execute("ALTER TABLE nostrclient.config RENAME COLUMN json_data TO extra")
    await db.execute(
        "ALTER TABLE nostrclient.config ADD COLUMN owner_id TEXT DEFAULT 'admin'"
    )
