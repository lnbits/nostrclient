# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`nostrclient` is an LNbits extension that acts as a Nostr relay multiplexer. It maintains persistent connections to multiple Nostr relays and allows clients to connect via a single WebSocket. Messages from the client are distributed to all connected relays, and responses are aggregated and sent back to the client.

## Development Commands

### Using `uv` (Modern Python Package Manager)
This project uses `uv` for dependency management. All commands should be prefixed with `uv run`.

### Common Development Tasks
```bash
# Format code (runs prettier, black, and ruff)
make format

# Run all checks (mypy, pyright, black, ruff, prettier)
make check

# Run tests
make test

# Individual formatting/checking
make black          # Format Python code
make ruff           # Fix Python linting issues
make prettier       # Format JS/JSON/etc.
make mypy           # Type check with mypy
make pyright        # Type check with pyright
make checkblack     # Check black formatting without changes
make checkruff      # Check ruff without fixes
make checkprettier  # Check prettier without changes

# Pre-commit hooks
make install-pre-commit-hook
make pre-commit
```

## Architecture

### Core Components

1. **NostrRouter** (`router.py:18-176`)
   - Manages individual WebSocket connections from clients
   - Rewrites subscription IDs to prevent conflicts between multiple clients
   - Maintains bidirectional message flow: client ↔ router ↔ relays
   - Two main async tasks per connection:
     - `_client_to_nostr()`: Receives from client, forwards to relays
     - `_nostr_to_client()`: Receives from relays, forwards to client
   - Handles REQ (subscribe), CLOSE (unsubscribe), and EVENT messages

2. **RelayManager** (`nostr/relay_manager.py:13-144`)
   - Manages connections to multiple Nostr relays
   - Each relay runs in separate threads (connection + queue worker)
   - Caches subscriptions and republishes them when new relays are added
   - Implements exponential backoff for relay reconnection (max 1 hour)
   - Handles relay failures and automatic restarts

3. **Background Tasks** (`tasks.py`)
   - `init_relays()`: Loads relays from database and connects
   - `subscribe_events()`: Sets up event/notice callbacks using MessagePool
   - `check_relays()`: Periodic health check (every 20s) for disconnected relays

4. **WebSocket Endpoints** (`views_api.py:116-163`)
   - Public endpoint: `/api/v1/relay` (if enabled in config)
   - Private endpoint: `/api/v1/{encrypted_id}` (requires valid encrypted ID)
   - WebSocket lifecycle tied to NostrRouter instance
   - Configurable via `Config` model (private_ws/public_ws flags)

### Message Flow

1. Client connects to WebSocket endpoint
2. NostrRouter created and started, added to `all_routers` list
3. Client sends subscription (REQ) → Router rewrites subscription ID → Sent to all relays
4. Relays send events → Router collects in `received_subscription_events` → Reconstructs with original ID → Sent to client
5. EOSE (End of Stored Events) messages aggregated in `received_subscription_eosenotices`
6. Client disconnects → Router stops → Subscriptions closed on all relays

### Database Schema

- `nostrclient.relays`: Stores relay URLs and active status
- `nostrclient.config`: Stores user configuration (owner_id, extra JSON)

### Nostr Module

The `nostr/` directory contains a vendored Nostr client library:
- `client/client.py`: Main NostrClient class
- `relay.py`: Individual relay connection handler
- `relay_manager.py`: Manages multiple relay connections
- `event.py`, `key.py`: Nostr event and cryptography utilities
- `message_pool.py`: Event/notice message aggregation

**Note**: The `nostr/` directory is excluded from mypy and ruff checks (see `pyproject.toml:26,56`).

## Testing

The extension includes a "Test Endpoint" feature (`views_api.py:84-113`) that allows users to:
- Send encrypted direct messages to themselves or test accounts
- Verify WebSocket functionality end-to-end
- Debug relay connections

## Important Patterns

1. **Subscription ID Rewriting**: All client subscription IDs are rewritten to prevent conflicts when multiple clients use the same IDs. Original IDs are stored in `NostrRouter.original_subscription_ids` dict.

2. **Thread Safety**: `RelayManager` uses `_subscriptions_lock` to protect subscription cache during concurrent access.

3. **Graceful Shutdown**: `nostrclient_stop()` in `__init__.py:25-39` cancels all tasks and closes all relay connections.

4. **Event Deduplication**: Events are deduplicated by event ID in `tasks.py:41-43` before adding to the subscription events list.

## Configuration

- **Type Checking**: Uses both mypy and pyright (configured in `pyproject.toml` and via npm)
- **Linting**: Ruff with specific rule set (F, E, W, I, A, C, N, UP, RUF, B)
- **Formatting**: Black (88 char line length) for Python, Prettier for other files
- **Python Version**: Requires >=3.10, <3.13
