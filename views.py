from fastapi import Request, Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

from lnbits.core.models import User
from lnbits.decorators import check_admin

from . import nostr_renderer, nostrclient_ext

templates = Jinja2Templates(directory="templates")


@nostrclient_ext.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_admin)):
    return nostr_renderer().TemplateResponse(
        "nostrclient/index.html", {"request": request, "user": user.dict()}
    )
