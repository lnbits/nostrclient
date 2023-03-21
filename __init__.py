import asyncio
from fastapi import APIRouter
from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import catch_everything_and_restart
from starlette.staticfiles import StaticFiles

db = Database("ext_nostrclient")

nostrclient_static_files = [
    {
        "path": "/nostrclient/static",
        "app": StaticFiles(directory="lnbits/extensions/nostrclient/static"),
        "name": "nostrclient_static",
    }
]

nostrclient_ext: APIRouter = APIRouter(prefix="/nostrclient", tags=["nostrclient"])


def nostr_renderer():
    return template_renderer(["lnbits/extensions/nostrclient/templates"])


from .tasks import init_relays, subscribe_events


def nostrclient_start():
    loop = asyncio.get_event_loop()
    loop.create_task(catch_everything_and_restart(init_relays))
    loop.create_task(catch_everything_and_restart(subscribe_events))
