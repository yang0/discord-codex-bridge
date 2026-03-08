# W Bridge Route Design

**Date:** 2026-03-08
**Status:** Approved for execution

## Goal

Create a dedicated Discord text channel for the tmux session `w_bridge` and register it as a new bridge route in the existing multi-bridge service.

## Current State

The bridge service already runs as a single Discord bot process with local-only route definitions in `bridges.local.json`.

Existing routes:
- `main` → channel `1479951053494554736` → tmux `oc_backup`
- `evolution` → channel `1479985018565820488` → tmux `w_evolution`

The bot can currently see one guild:
- `旺德福龙虾网络`

That guild already has a `Text Channels` category containing the current bridge channels.

## Approved Approach

Use the existing guild and existing `Text Channels` category, then:

1. create a new Discord text channel named `w-bridge`;
2. capture its new `channel_id`;
3. add a third route to `bridges.local.json`;
4. point that route at tmux session `w_bridge`;
5. use a dedicated route state file at `./state/bridge_state_w_bridge.json`;
6. reload or restart the service only if runtime hot reload does not pick the change up automatically.

## Why This Approach

- It keeps one tmux session mapped to one Discord channel, consistent with the current design.
- It avoids reusing an existing channel and accidentally mixing workflows.
- It preserves the repository privacy model because only local-only config files need real ids.

## Route Shape

The new route should look like:

```json
{
  "name": "w-bridge",
  "enabled": true,
  "channel_id": "<new discord channel id>",
  "tmux_session": "w_bridge",
  "state_path": "./state/bridge_state_w_bridge.json"
}
```

## Risks

- The bot token might lack permission to create channels in the guild.
- The running service might need a restart if the current process does not notice the config file update quickly enough.
- The tmux session `w_bridge` might not exist or might not contain the expected interactive pane.

## Validation

Success means:

1. Discord contains a new text channel named `w-bridge`;
2. `bridges.local.json` contains a valid new route for that channel;
3. the bridge service recognizes the route;
4. the tmux session `w_bridge` is reachable by the service.
