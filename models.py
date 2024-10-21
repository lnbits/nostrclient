from typing import Optional

from lnbits.helpers import urlsafe_short_hash
from pydantic import BaseModel


class RelayStatus(BaseModel):
    num_sent_events: Optional[int] = 0
    num_received_events: Optional[int] = 0
    error_counter: Optional[int] = 0
    error_list: Optional[list] = []
    notice_list: Optional[list] = []


class Relay(BaseModel):
    id: Optional[str] = None
    url: Optional[str] = None
    connected: Optional[bool] = None
    connected_string: Optional[str] = None
    status: Optional[RelayStatus] = None
    active: Optional[bool] = None
    ping: Optional[int] = None

    def _init__(self):
        if not self.id:
            self.id = urlsafe_short_hash()


class RelayDb(BaseModel):
    id: str
    url: str
    active: Optional[bool] = True


class TestMessage(BaseModel):
    sender_private_key: Optional[str]
    reciever_public_key: str
    message: str


class TestMessageResponse(BaseModel):
    private_key: str
    public_key: str
    event_json: str


class Config(BaseModel):
    private_ws: bool = True
    public_ws: bool = False
