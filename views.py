from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from lnbits.core.crud.users import get_user_from_account
from lnbits.core.models.users import Account
from lnbits.decorators import check_admin
from lnbits.helpers import template_renderer

nostrclient_generic_router = APIRouter()


def nostr_renderer():
    return template_renderer(["nostrclient/templates"])


@nostrclient_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, account: Account = Depends(check_admin)):
    user = await get_user_from_account(account)
    if not user:
        return HTMLResponse("No user found", status_code=404)
    return nostr_renderer().TemplateResponse(
        "nostrclient/index.html", {"request": request, "user": user.json()}
    )
