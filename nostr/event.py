import json
import time
from dataclasses import dataclass, field
from enum import IntEnum
from hashlib import sha256

from nostr_sdk import Event as SdkEvent

from .message_type import ClientMessageType


class EventKind(IntEnum):
    SET_METADATA = 0
    TEXT_NOTE = 1
    RECOMMEND_RELAY = 2
    CONTACTS = 3
    ENCRYPTED_DIRECT_MESSAGE = 4
    DELETE = 5


@dataclass
class Event:
    content: str | None = None
    public_key: str | None = None
    created_at: int | None = None
    kind: int = EventKind.TEXT_NOTE
    tags: list[list[str]] = field(default_factory=list)
    signature: str | None = None

    def __post_init__(self):
        if self.content is not None and not isinstance(self.content, str):
            raise TypeError("Argument 'content' must be of type str")

        if self.created_at is None:
            self.created_at = int(time.time())

    @staticmethod
    def serialize(
        public_key: str, created_at: int, kind: int, tags: list[list[str]], content: str
    ) -> bytes:
        data = [0, public_key, created_at, kind, tags, content]
        data_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return data_str.encode()

    @staticmethod
    def compute_id(
        public_key: str, created_at: int, kind: int, tags: list[list[str]], content: str
    ):
        return sha256(
            Event.serialize(public_key, created_at, kind, tags, content)
        ).hexdigest()

    @property
    def id(self) -> str:
        assert self.public_key
        assert self.created_at
        assert self.content
        return Event.compute_id(
            self.public_key, self.created_at, self.kind, self.tags, self.content
        )

    def add_pubkey_ref(self, pubkey: str):
        self.tags.append(["p", pubkey])

    def add_event_ref(self, event_id: str):
        self.tags.append(["e", event_id])

    def verify(self) -> bool:
        return SdkEvent.from_json(json.dumps(self.to_dict())).verify()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pubkey": self.public_key,
            "created_at": self.created_at,
            "kind": self.kind,
            "tags": self.tags,
            "content": self.content,
            "sig": self.signature,
        }

    def to_message(self) -> str:
        return json.dumps([ClientMessageType.EVENT, self.to_dict()])


@dataclass
class EncryptedDirectMessage(Event):
    recipient_pubkey: str | None = None
    cleartext_content: str | None = None
    reference_event_id: str | None = None

    def __post_init__(self):
        if self.content is not None:
            self.cleartext_content = self.content
            self.content = None

        if self.recipient_pubkey is None:
            raise Exception("Must specify a recipient_pubkey.")

        self.kind = EventKind.ENCRYPTED_DIRECT_MESSAGE
        super().__post_init__()
        self.add_pubkey_ref(self.recipient_pubkey)

        if self.reference_event_id is not None:
            self.add_event_ref(self.reference_event_id)

    @property
    def id(self) -> str:
        if self.content is None:
            raise Exception(
                "EncryptedDirectMessage `id` is undefined until its"
                + " message is encrypted and stored in the `content` field"
            )
        return super().id
