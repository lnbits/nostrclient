## Nostr Relay Multiplexer

An always-on relay multiplexer that simplifies connecting to multiple Nostr relays.

Instead of your Nostr client managing connections to dozens of relays, you connect to a single WebSocket endpoint provided by `nostrclient`, which then fans out your requests to all configured relays and aggregates the responses back to you.

### Benefits

- **Simplified Client Configuration** - Connect to one endpoint instead of managing multiple relay connections
- **Always-On Connectivity** - Your LNbits instance maintains persistent connections to relays
- **Resource Efficient** - Share relay connections across multiple clients
- **Automatic Subscription Management** - Subscription ID rewriting prevents conflicts between clients
