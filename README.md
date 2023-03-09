# nostrclient

`nostrclient` can open multiple connections to nostr relays and act as a multiplexer for other clients: A client can open a single websocket to `nostrclient` which then sends the data to multiple relays. The responses from these relays are then sent back to the client.
