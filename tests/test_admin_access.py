from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from lnbits.decorators import check_account_exists
from lnbits.settings import settings

from .. import nostrclient_ext


@pytest.mark.parametrize("user_id, status", [(None, 401), ("ordinary", 403)])
def test_management_routes_reject_non_admins(monkeypatch, user_id, status):
    monkeypatch.setattr(settings, "super_user", "superuser")
    monkeypatch.setattr(settings, "lnbits_admin_users", ["admin"])
    app = FastAPI()
    app.include_router(nostrclient_ext)

    async def account():
        if user_id is None:
            raise HTTPException(401, "Authentication required")
        return SimpleNamespace(id=user_id, has_password=True)

    app.dependency_overrides[check_account_exists] = account
    with TestClient(app) as client:
        for route in nostrclient_ext.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                response = client.request(method, route.path)
                assert response.status_code == status, (
                    method,
                    route.path,
                    response.text,
                )


@pytest.mark.parametrize("user_id", ["admin", "superuser"])
def test_admin_can_list_relays(monkeypatch, user_id):
    monkeypatch.setattr(settings, "super_user", "superuser")
    monkeypatch.setattr(settings, "lnbits_admin_users", ["admin"])
    app = FastAPI()
    app.include_router(nostrclient_ext)

    async def account():
        return SimpleNamespace(id=user_id, has_password=True)

    app.dependency_overrides[check_account_exists] = account
    with TestClient(app) as client:
        response = client.get("/nostrclient/api/v1/relays")
    assert response.status_code == 200
