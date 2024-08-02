from .nostr.client.client import NostrClient
from .router import NostrRouter

nostr_client: NostrClient = NostrClient()
all_routers: list[NostrRouter] = []
