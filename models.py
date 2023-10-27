from sqlite3 import Row
from typing import List, Optional

from pydantic import BaseModel, Field

from lnbits.helpers import urlsafe_short_hash


class RelayStatus(BaseModel):
    num_sent_events: Optional[int] = 0
    num_received_events: Optional[int] = 0
    error_counter: Optional[int] = 0
    error_list: Optional[List] = []
    notice_list: Optional[List] = []


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

    @classmethod
    def from_row(cls, row: Row) -> "Relay":
        return cls(**dict(row))


class Event(BaseModel):
    content: str
    pubkey: str
    created_at: Optional[int]
    kind: int
    tags: Optional[List[List[str]]]
    sig: str


class Filter(BaseModel):
    ids: Optional[List[str]]
    kinds: Optional[List[int]]
    authors: Optional[List[str]]
    since: Optional[int]
    until: Optional[int]
    e: Optional[List[str]] = Field(alias="#e")
    p: Optional[List[str]] = Field(alias="#p")
    limit: Optional[int]


class Filters(BaseModel):
    __root__: List[Filter]


class TestMessage(BaseModel):
    sender_private_key: Optional[str]
    reciever_public_key: str
    message: str


class TestMessageResponse(BaseModel):
    private_key: str
    public_key: str
    event_json: str
