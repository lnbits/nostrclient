from fastapi import APIRouter

from .. import nostrclient_ext


# just import router and add it to a test router
def test_router():
    router = APIRouter()
    router.include_router(nostrclient_ext)
