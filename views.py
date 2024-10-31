from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_admin
from lnbits.helpers import template_renderer

nostrclient_generic_router = APIRouter()


def nostr_renderer():
    return template_renderer(["nostrclient/templates"])


@nostrclient_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_admin)):
    return nostr_renderer().TemplateResponse(
        "nostrclient/index.html", {"request": request, "user": user.json()}
    )
