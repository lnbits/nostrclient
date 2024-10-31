import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .router import all_routers, nostr_client
from .tasks import check_relays, init_relays, subscribe_events
from .views import nostrclient_generic_router
from .views_api import nostrclient_api_router

nostrclient_static_files = [
    {
        "path": "/nostrclient/static",
        "name": "nostrclient_static",
    }
]

nostrclient_ext: APIRouter = APIRouter(prefix="/nostrclient", tags=["nostrclient"])
nostrclient_ext.include_router(nostrclient_generic_router)
nostrclient_ext.include_router(nostrclient_api_router)
scheduled_tasks: list[asyncio.Task] = []


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
    from lnbits.tasks import create_permanent_unique_task

    task1 = create_permanent_unique_task("ext_nostrclient_init_relays", init_relays)
    task2 = create_permanent_unique_task(
        "ext_nostrclient_subscrive_events", subscribe_events
    )
    task3 = create_permanent_unique_task("ext_nostrclient_check_relays", check_relays)
    scheduled_tasks.extend([task1, task2, task3])


__all__ = [
    "db",
    "nostrclient_ext",
    "nostrclient_static_files",
    "nostrclient_stop",
    "nostrclient_start",
]
