import asyncio
from typing import List

from fastapi import APIRouter
from loguru import logger

from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import create_permanent_unique_task

from .nostr.client.client import NostrClient
from .router import NostrRouter

db = Database("ext_nostrclient")

nostrclient_static_files = [
    {
        "path": "/nostrclient/static",
        "name": "nostrclient_static",
    }
]

nostrclient_ext: APIRouter = APIRouter(prefix="/nostrclient", tags=["nostrclient"])

nostr_client: NostrClient = NostrClient()

# we keep this in
all_routers: list[NostrRouter] = []
scheduled_tasks: list[asyncio.Task] = []


def nostr_renderer():
    return template_renderer(["nostrclient/templates"])


from .tasks import check_relays, init_relays, subscribe_events  # noqa
from .views import *  # noqa
from .views_api import *  # noqa


async def nostrclient_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)

    for router in all_routers:
        try:
            await router.stop()
            all_routers.remove(router)
        except Exception as e:
            logger.error(e)

    nostr_client.close()


def nostrclient_start():
    task1 = create_permanent_unique_task("ext_nostrclient_init_relays", init_relays)
    task2 = create_permanent_unique_task("ext_nostrclient_subscrive_events", subscribe_events)
    task3 = create_permanent_unique_task("ext_nostrclient_check_relays", check_relays)
    scheduled_tasks.extend([task1, task2, task3])
