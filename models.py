from lnbits.helpers import urlsafe_short_hash
from pydantic import BaseModel, Field


class RelayStatus(BaseModel):
    num_sent_events: int | None = 0
    num_received_events: int | None = 0
    error_counter: int | None = 0
    error_list: list | None = []
    notice_list: list | None = []


class Relay(BaseModel):
    id: str | None = None
    url: str | None = None
    active: bool | None = None

    connected: bool | None = Field(default=None, no_database=True)
    connected_string: str | None = Field(default=None, no_database=True)
    status: RelayStatus | None = Field(default=None, no_database=True)

    ping: int | None = Field(default=None, no_database=True)

    def _init__(self):
        if not self.id:
            self.id = urlsafe_short_hash()


class RelayDb(BaseModel):
    id: str
    url: str
    active: bool | None = True


class TestMessage(BaseModel):
    sender_private_key: str | None
    reciever_public_key: str
    message: str


class TestMessageResponse(BaseModel):
    private_key: str
    public_key: str
    event_json: str


class Config(BaseModel):
    private_ws: bool = True
    public_ws: bool = False


class UserConfig(BaseModel):
    owner_id: str
    extra: Config = Config()
