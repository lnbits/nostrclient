async def m001_initial(db):
    """
    Initial nostrclient table.
    """
    await db.execute(
        f"""
        CREATE TABLE nostrclient.relays (
            id TEXT NOT NULL PRIMARY KEY,
            url TEXT NOT NULL,
            active BOOLEAN DEFAULT true
        );
    """
    )
