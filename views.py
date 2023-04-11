import asyncio
from http import HTTPStatus

# FastAPI good for incoming
from fastapi import Request
from fastapi.param_functions import Query
from fastapi.params import Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

from lnbits.core.crud import update_payment_status
from lnbits.core.models import User
from lnbits.core.views.api import api_payment
from lnbits.decorators import check_admin, check_user_exists

from . import nostr_renderer, nostrclient_ext

templates = Jinja2Templates(directory="templates")


@nostrclient_ext.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_admin)):
    return nostr_renderer().TemplateResponse(
        "nostrclient/index.html", {"request": request, "user": user.dict()}
    )
