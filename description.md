An always-on relay multiplexer that simplifies connecting to multiple Nostr relays.

Other LNbits extensions like **Nostr Market** and **NWC Provider** use this extension to communicate on Nostr. You can also connect your own Nostr client to the WebSocket endpoint, which fans out your requests to all configured relays and aggregates the responses.

- **Simplified Client Configuration** - Connect to one endpoint instead of managing multiple relay connections
- **Always-On Connectivity** - Your LNbits instance maintains persistent connections to relays
- **Resource Efficient** - Share relay connections across multiple clients
- **Automatic Subscription Management** - Subscription ID rewriting prevents conflicts between clients
