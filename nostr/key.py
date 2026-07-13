import secrets

import coincurve
from nostr_sdk import (
    Keys,
    PublicKey as SdkPublicKey,
    SecretKey,
    nip04_decrypt,
    nip04_encrypt,
)

from .event import EncryptedDirectMessage, Event, EventKind


class PublicKey:
    def __init__(self, raw_bytes: bytes) -> None:
        self.raw_bytes = raw_bytes

    def bech32(self) -> str:
        return SdkPublicKey.from_bytes(self.raw_bytes).to_bech32()

    def hex(self) -> str:
        return self.raw_bytes.hex()

    def verify_signed_message_hash(self, message_hash: str, sig: str) -> bool:
        try:
            return coincurve.PublicKeyXOnly(self.raw_bytes).verify(
                bytes.fromhex(sig), bytes.fromhex(message_hash)
            )
        except Exception:
            return False

    @classmethod
    def from_npub(cls, npub: str):
        return cls(bytes.fromhex(SdkPublicKey.parse(npub).to_hex()))


class PrivateKey:
    def __init__(self, raw_secret: bytes | None = None) -> None:
        self.raw_secret = (
            raw_secret if raw_secret is not None else secrets.token_bytes(32)
        )
        self._keys = Keys(SecretKey.from_bytes(self.raw_secret))
        self.public_key = PublicKey(bytes.fromhex(self._keys.public_key().to_hex()))

    @classmethod
    def from_nsec(cls, nsec: str):
        return cls(bytes.fromhex(SecretKey.parse(nsec).to_hex()))

    def bech32(self) -> str:
        return self._keys.secret_key().to_bech32()

    def hex(self) -> str:
        return self.raw_secret.hex()

    def tweak_add(self, scalar: bytes) -> bytes:
        sk = coincurve.PrivateKey(self.raw_secret)
        return sk.add(scalar).to_der()

    def compute_shared_secret(self, public_key_hex: str) -> bytes:
        pk = coincurve.PublicKey(bytes.fromhex("02" + public_key_hex))
        sk = coincurve.PrivateKey(self.raw_secret)
        return sk.ecdh(pk.format())

    def encrypt_message(self, message: str, public_key_hex: str) -> str:
        return nip04_encrypt(
            self._keys.secret_key(), SdkPublicKey.parse(public_key_hex), message
        )

    def encrypt_dm(self, dm: EncryptedDirectMessage) -> None:
        assert dm.cleartext_content
        assert dm.recipient_pubkey
        dm.content = self.encrypt_message(
            message=dm.cleartext_content, public_key_hex=dm.recipient_pubkey
        )

    def decrypt_message(self, encoded_message: str, public_key_hex: str) -> str:
        return nip04_decrypt(
            self._keys.secret_key(),
            SdkPublicKey.parse(public_key_hex),
            encoded_message,
        )

    def sign_message_hash(self, message_hash: bytes) -> str:
        return self._keys.sign_schnorr(message_hash)

    def sign_event(self, event: Event) -> None:
        if event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE and event.content is None:
            self.encrypt_dm(event)  # type: ignore[arg-type]
        if event.public_key is None:
            event.public_key = self.public_key.hex()
        event.signature = self.sign_message_hash(bytes.fromhex(event.id))

    def __eq__(self, other):
        return self.raw_secret == other.raw_secret


def mine_vanity_key(prefix: str | None = None, suffix: str | None = None) -> PrivateKey:
    if prefix is None and suffix is None:
        raise ValueError("Expected at least one of 'prefix' or 'suffix' arguments")

    while True:
        sk = PrivateKey()
        if (
            prefix is not None
            and not sk.public_key.bech32()[5 : 5 + len(prefix)] == prefix
        ):
            continue
        if suffix is not None and not sk.public_key.bech32()[-len(suffix) :] == suffix:
            continue
        break

    return sk
