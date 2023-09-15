# Nostrclient - <small>[LNbits](https://github.com/lnbits/lnbits) extension</small>

<small>For more about LNBits extension check [this tutorial](https://github.com/lnbits/lnbits/wiki/LNbits-Extensions)</small>

`nostrclient` is an always-on extension that can open multiple connections to nostr relays and act as a multiplexer for other clients: You open a single websocket to `nostrclient` which then sends the data to multiple relays. The responses from these relays are then sent back to the client.

![2023-03-08 18 11 07](https://user-images.githubusercontent.com/93376500/225265727-369f0f8a-196e-41df-a0d1-98b50a0228be.jpg)

### Troubleshoot

The `Test Endpoint` functionality heps the user to check that the `nostrclient` web-socket endpoint works as expected.

The LNbits user can DM itself (or a temp account) from `nostrclient` and verify that the messages are sent and received correctly.

https://user-images.githubusercontent.com/2951406/236780745-929c33c2-2502-49be-84a3-db02a7aabc0e.mp4
