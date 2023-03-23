# nostrclient

`nostrclient` is an always-on extension that can open multiple connections to nostr relays and act as a multiplexer for other clients: You open a single websocket to `nostrclient` which then sends the data to multiple relays. The responses from these relays are then sent back to the client.



![2023-03-08 18 11 07](https://user-images.githubusercontent.com/93376500/225265727-369f0f8a-196e-41df-a0d1-98b50a0228be.jpg)
