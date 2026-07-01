from nostr_sdk import (
    ClientMessage,
    EventBuilder,
    Keys,
    Kind,
    PublicKey,
    SecretKey,
    Tag,
    nip04_encrypt,
)


def create_encrypted_dm_message(
    sender_private_key: str | None, recipient_public_key: str, message: str
) -> tuple[str, str, str]:
    try:
        keys = (
            Keys(SecretKey.parse(sender_private_key))
            if sender_private_key
            else Keys.generate()
        )
        recipient = PublicKey.parse(recipient_public_key)
        content = nip04_encrypt(keys.secret_key(), recipient, message)
        event = (
            EventBuilder(Kind(4), content)
            .tags([Tag.public_key(recipient)])
            .sign_with_keys(keys)
        )
    except Exception as ex:
        raise ValueError("Cannot generate encrypted direct message event") from ex

    return (
        keys.secret_key().to_hex(),
        recipient.to_hex(),
        ClientMessage.event(event).as_json(),
    )
