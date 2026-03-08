# Discord Multi-Bridge Design

**Date:** 2026-03-08
**Status:** Approved for planning

## Goal

Replace the current one-service-per-channel Discord↔tmux bridge setup with a single long-running service that can manage multiple bridge routes in one process.

Each route should behave independently:
- one Discord channel maps to one tmux target
- each route keeps its own active task, queue, cadence, and state file
- routes do not block each other
- route config supports hot reload without restarting the process

## Hard Constraints

- Do not expose private runtime data to the repository.
- Real bot tokens, real Discord channel ids, real tmux session names, and real local state paths must stay in local-only files.
- The new multi-bridge service should directly replace the current per-channel services instead of running permanently alongside them.
- Configuration changes should be applied with hot reload, not by restarting the service.

## Current State

The current project is a single-route bridge service:
- one `.env` file provides one `DISCORD_CHANNEL_ID` and one tmux target
- one `discord.py` client listens for messages from exactly one configured channel
- one `BridgeController` manages exactly one in-memory queue and one active task
- one `JsonStateStore` persists a single active task plus queue to one JSON state file
- one systemd user unit runs one process per bridge

This model works for isolated bridges, but scaling it requires duplicated `.env` files, duplicated systemd units, and duplicated runtime processes.

## Recommended Approach

Use one Discord client process that loads a local-only route table and maintains a separate runtime controller per route.

### Why this approach

- It preserves the current runtime model and test surface instead of rewriting the bridge from scratch.
- It keeps each route independent while consolidating the service process and Discord connection.
- It supports hot reload by diffing route config in memory.
- It provides a clean migration path from existing per-channel services.

## Configuration Model

### Shared environment file

Keep a single local `.env` file for global runtime settings only:
- `DISCORD_BOT_TOKEN`
- `TMUX_BIN`
- default intervals and capture sizes
- optional path to the route config file

### Local-only route file

Add a new local-only JSON file, recommended name:
- `bridges.local.json`

Repository example file:
- `bridges.example.json`

Recommended structure:

```json
{
  "defaults": {
    "tmux_window": 0,
    "tmux_pane": 0,
    "check_interval_sec": 5,
    "progress_interval_sec": 300,
    "progress_capture_lines": 220,
    "completion_lines": 100
  },
  "bridges": [
    {
      "name": "backup",
      "enabled": true,
      "channel_id": 123456789012345678,
      "tmux_session": "session_alpha",
      "state_path": "./state/bridge_state_backup.json"
    },
    {
      "name": "evolution",
      "enabled": true,
      "channel_id": 234567890123456789,
      "tmux_session": "session_beta",
      "state_path": "./state/bridge_state_evolution.json"
    }
  ]
}
```

### Privacy rules

The repository should only contain:
- `.env.example`
- `bridges.example.json`
- docs and tests with placeholder ids

The repository should ignore:
- `.env`
- `.env.*`
- `bridges.local.json`
- `state/*.json`

## Runtime Architecture

### Core objects

Add a route-aware runtime layer:

- `BridgeRouteConfig`
  - one resolved route definition
- `BridgeRuntime`
  - holds per-route controller, state store, resolved tmux settings, and live config snapshot
- `MultiBridgeService`
  - owns the Discord client lifecycle, hot reload checks, route registry, and dispatch loop

### Runtime registry

The service should keep a map keyed by Discord channel id:

- `channel_id -> BridgeRuntime`

This lets the Discord event handler route incoming messages directly to the correct bridge runtime.

### Per-route isolation

Each route must have its own:
- `BridgeController`
- `BridgeState`
- `JsonStateStore`
- progress timer cadence
- completion excerpt generation
- queue and active task lifecycle

If route A is busy, route B must still be able to dispatch immediately to its own tmux target.

## Data Flow

### Startup

1. Load `.env`
2. Resolve the route config file path
3. Load and validate `bridges.local.json`
4. Build one `BridgeRuntime` per enabled route
5. Load each route's state file independently
6. Start one Discord client and one periodic observer loop

### Inbound Discord message

1. Receive message from Discord
2. Ignore bot-authored messages
3. Look up `message.channel.id` in the route registry
4. If no route matches, ignore the message
5. Convert message to `DiscordRequest`
6. Submit request to that route's controller
7. Apply returned effects only for that route

### Periodic observation loop

On each tick:
1. Check whether the route config file changed
2. Reload routes if needed
3. For each active route:
   - resolve tmux target
   - inspect running state
   - ask the controller for effects
   - send Discord updates and dispatch next work as needed
   - persist route state

## Hot Reload Behavior

### Reload trigger

Use file modification time on `bridges.local.json`.

A lightweight mtime check is enough for the current scope and avoids an extra watcher dependency.

### Reload diff rules

When config changes:
- **Added route:** create a new `BridgeRuntime` and load its state
- **Removed route:** mark disabled; if idle, remove immediately; if active or queued, drain and remove after completion
- **Updated route:**
  - for simple field changes such as cadence or excerpt line counts, update in place
  - for identity changes such as `channel_id` or `tmux_session`, create a replacement runtime and gracefully retire the old one

### Safety rule

Do not interrupt a running task just because config changed.

If a route is removed or materially changed while active, it should finish its current task and queued items before shutdown unless the route is explicitly disabled with forced behavior in a future version.

## Migration Plan

The migration should replace the current two-instance setup:
- `discord-codex-bridge.service`
- `discord-codex-evolution.service`

Target replacement service:
- `discord-codex-multi-bridge.service`

The local route file should contain both current bridges.

After verification:
- stop and disable old services
- enable the new multi-bridge service
- keep old env files only until the new service is confirmed stable

## Error Handling

### Route-local failures

Failures such as tmux resolution errors or state save failures should be reported only to the affected route channel and should not crash unrelated routes.

### Global failures

Failures such as malformed global config, missing Discord token, or unreadable route file at startup should fail the process loudly and be visible in systemd logs.

### Reload failures

If hot reload sees an invalid config file, the service should:
- keep the last known-good config in memory
- log the validation error
- avoid replacing live routes with a broken config

## Testing Strategy

### Unit tests

Add tests for:
- route config parsing and validation
- channel id to route runtime lookup
- per-route controller isolation
- hot reload add/remove/update behavior
- last-known-good config retention on invalid reload
- privacy-oriented config path behavior for local-only files

### Runtime tests

Add tests for:
- service ignores messages from unknown channels
- service dispatches concurrent work to separate routes independently
- route A progress updates do not affect route B state
- disabled route drains safely when active work exists

### Regression tests

Preserve existing single-route behavior through the multi-route abstraction by ensuring one-route config still behaves like the original bridge.

## Files Expected to Change During Implementation

Likely runtime files:
- `src/discord_codex_bridge/config.py`
- `src/discord_codex_bridge/models.py`
- `src/discord_codex_bridge/controller.py`
- `src/discord_codex_bridge/state.py`
- `src/discord_codex_bridge/service.py`
- `src/discord_codex_bridge/__main__.py`

Likely test files:
- `tests/test_runtime_helpers.py`
- `tests/test_service_helpers.py`
- `tests/test_service_runtime_commands.py`
- new route-config and hot-reload tests if needed

Likely config/docs files:
- `.gitignore`
- `.env.example`
- `bridges.example.json`
- `README.md`
- `systemd/discord-codex-multi-bridge.service`

## Non-Goals

- No cross-route global queue
- No shared fairness scheduler across all bridges
- No external database
- No remote configuration service
- No route-level permission system beyond explicit channel mapping

## Recommendation

Proceed with a single-process multi-route architecture built on top of the current bridge primitives.

This gives the requested operational model with the smallest behavior delta, the lowest migration risk, and a clean privacy boundary between repo-safe templates and local-only runtime data.
