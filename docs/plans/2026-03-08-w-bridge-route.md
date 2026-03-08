# W Bridge Route Implementation Plan

> **Execution Skill:** Use `superpowers:subagent-driven-development` (same session) or `superpowers:executing-plans` (separate session) to implement this plan task-by-task.

**Goal:** Create a new Discord channel for `w_bridge` and attach it to the existing multi-bridge runtime with local-only configuration.

**Architecture:** Reuse the existing Discord guild and multi-route JSON config. Create one additional Discord text channel, append one route entry in `bridges.local.json`, then verify the service can resolve the channel and tmux target.

**Tech Stack:** Discord HTTP API, local JSON config, tmux, Python bridge service, systemd user service

---

### Task 1: Create the Discord text channel

**Files:**
- Modify: none
- Verify: live Discord guild `旺德福龙虾网络`

**Step 1: Discover the target guild and category**

Confirm the bot can see the existing guild and `Text Channels` category so the new channel lands beside current bridge routes.

**Step 2: Create the channel**

Create a new Discord text channel named `w-bridge` under the existing text-channel category.

**Step 3: Capture the new channel id**

Record the returned `channel_id` for local configuration.

**Step 4: Verify creation**

Fetch guild channels again and confirm `w-bridge` exists in the expected category.

### Task 2: Register the new local bridge route

**Files:**
- Modify: `bridges.local.json`

**Step 1: Append the route**

Add a new enabled route with:
- `name`: `w-bridge`
- `channel_id`: the new Discord channel id
- `tmux_session`: `w_bridge`
- `state_path`: `./state/bridge_state_w_bridge.json`

**Step 2: Keep defaults unchanged**

Do not change global defaults or existing routes.

**Step 3: Verify config integrity**

Load the JSON and confirm route names and channel ids remain unique.

### Task 3: Verify runtime pickup

**Files:**
- Modify: none unless runtime restart is required
- Verify: `.env`, `bridges.local.json`, tmux runtime, `systemd/discord-codex-multi-bridge.service`

**Step 1: Confirm tmux session exists**

Verify session `w_bridge` is present and resolvable.

**Step 2: Check service status**

Confirm the bridge service is running.

**Step 3: Wait for hot reload or restart if needed**

Use the existing runtime behavior to pick up the config change. If the route does not appear, restart the user service once.

**Step 4: Verify end-to-end readiness**

Confirm the route is active in config, Discord, and tmux so the channel is ready for use.

### Task 4: Record the operational result

**Files:**
- Modify: none

**Step 1: Summarize created assets**

Report the new channel name, channel id, config entry, and whether restart was needed.

**Step 2: Call out remaining manual follow-up if any**

If message-level smoke testing is still needed, note the exact next action for the operator.
