from typing import List
from fastapi import APIRouter
from starlette.staticfiles import StaticFiles

from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import catch_everything_and_restart

db = Database("ext_nostrclient")

nostrclient_static_files = [
    {
        "path": "/nostrclient/static",
        "app": StaticFiles(directory="lnbits/extensions/nostrclient/static"),
        "name": "nostrclient_static",
    }
]

nostrclient_ext: APIRouter = APIRouter(prefix="/nostrclient", tags=["nostrclient"])

scheduled_tasks: List[asyncio.Task] = []


def nostr_renderer():
    return template_renderer(["lnbits/extensions/nostrclient/templates"])


from .tasks import init_relays, subscribe_events
from .views import *  # noqa
from .views_api import *  # noqa


def nostrclient_start():
    loop = asyncio.get_event_loop()
    task1 = loop.create_task(catch_everything_and_restart(init_relays))
    scheduled_tasks.append(task1)
    task2 = loop.create_task(catch_everything_and_restart(subscribe_events))
    scheduled_tasks.append(task2)
