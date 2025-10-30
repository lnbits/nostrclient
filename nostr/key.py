import base64
import secrets

import coincurve
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .bech32 import Encoding, bech32_decode, bech32_encode, convertbits
from .event import EncryptedDirectMessage, Event, EventKind


class PublicKey:
    def __init__(self, raw_bytes: bytes) -> None:
        self.raw_bytes = raw_bytes

    def bech32(self) -> str:
        converted_bits = convertbits(self.raw_bytes, 8, 5)
        return bech32_encode("npub", converted_bits, Encoding.BECH32)

    def hex(self) -> str:
        return self.raw_bytes.hex()

    def verify_signed_message_hash(self, message_hash: str, sig: str) -> bool:
        pk = coincurve.PublicKeyXOnly(b"\x02" + self.raw_bytes)
        return pk.verify(bytes.fromhex(sig), bytes.fromhex(message_hash))

    @classmethod
    def from_npub(cls, npub: str):
        """Load a PublicKey from its bech32/npub form"""
        _, data, _ = bech32_decode(npub)
        raw_data = convertbits(data, 5, 8)
        assert raw_data
        raw_public_key = raw_data[:-1]
        return cls(bytes(raw_public_key))


class PrivateKey:
    def __init__(self, raw_secret: bytes | None = None) -> None:
        if raw_secret is not None:
            self.raw_secret = raw_secret
        else:
            self.raw_secret = secrets.token_bytes(32)

        sk = coincurve.PrivateKey(self.raw_secret)
        assert sk.public_key
        self.public_key = PublicKey(sk.public_key.format()[1:])

    @classmethod
    def from_nsec(cls, nsec: str):
        """Load a PrivateKey from its bech32/nsec form"""
        _, data, _ = bech32_decode(nsec)
        raw_data = convertbits(data, 5, 8)
        assert raw_data
        raw_secret = raw_data[:-1]
        return cls(bytes(raw_secret))

    def bech32(self) -> str:
        converted_bits = convertbits(self.raw_secret, 8, 5)
        return bech32_encode("nsec", converted_bits, Encoding.BECH32)

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
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(message.encode()) + padder.finalize()

        iv = secrets.token_bytes(16)
        cipher = Cipher(
            algorithms.AES(self.compute_shared_secret(public_key_hex)), modes.CBC(iv)
        )

        encryptor = cipher.encryptor()
        encrypted_message = encryptor.update(padded_data) + encryptor.finalize()

        return (
            f"{base64.b64encode(encrypted_message).decode()}"
            + f"?iv={base64.b64encode(iv).decode()}"
        )

    def encrypt_dm(self, dm: EncryptedDirectMessage) -> None:
        assert dm.cleartext_content
        assert dm.recipient_pubkey
        dm.content = self.encrypt_message(
            message=dm.cleartext_content, public_key_hex=dm.recipient_pubkey
        )

    def decrypt_message(self, encoded_message: str, public_key_hex: str) -> str:
        encoded_data = encoded_message.split("?iv=")
        encoded_content, encoded_iv = encoded_data[0], encoded_data[1]

        iv = base64.b64decode(encoded_iv)
        cipher = Cipher(
            algorithms.AES(self.compute_shared_secret(public_key_hex)), modes.CBC(iv)
        )
        encrypted_content = base64.b64decode(encoded_content)

        decryptor = cipher.decryptor()
        decrypted_message = decryptor.update(encrypted_content) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        unpadded_data = unpadder.update(decrypted_message) + unpadder.finalize()

        return unpadded_data.decode()

    def sign_message_hash(self, message_hash: bytes) -> str:
        sk = coincurve.PrivateKey(self.raw_secret)
        sig = sk.sign_schnorr(message_hash)
        return sig.hex()

    def sign_event(self, event: Event) -> None:
        if event.kind == EventKind.ENCRYPTED_DIRECT_MESSAGE and event.content is None:
            self.encrypt_dm(event)  # type: ignore
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
