import asyncio
from typing import List

from fastapi import APIRouter

from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import catch_everything_and_restart

from .nostr.client.client import NostrClient as NostrClientLib

db = Database("ext_nostrclient")

nostrclient_static_files = [
    {
        "path": "/nostrclient/static",
        "name": "nostrclient_static",
    }
]

nostrclient_ext: APIRouter = APIRouter(prefix="/nostrclient", tags=["nostrclient"])

scheduled_tasks: List[asyncio.Task] = []


# remove!
class NostrClient:
    def __init__(self):
        self.client: NostrClientLib = NostrClientLib()


nostr = NostrClient()


def nostr_renderer():
    return template_renderer(["nostrclient/templates"])


from .tasks import check_relays, init_relays, subscribe_events  # noqa
from .views import *  # noqa
from .views_api import *  # noqa


def nostrclient_start():
    loop = asyncio.get_event_loop()
    task1 = loop.create_task(catch_everything_and_restart(init_relays))
    scheduled_tasks.append(task1)
    task2 = loop.create_task(catch_everything_and_restart(subscribe_events))
    scheduled_tasks.append(task2)
    task3 = loop.create_task(catch_everything_and_restart(check_relays))
    scheduled_tasks.append(task3)
