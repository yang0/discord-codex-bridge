# Discord Multi-Bridge Implementation Plan

> **Execution Skill:** Use `superpowers:subagent-driven-development` (same session) or `superpowers:executing-plans` (separate session) to implement this plan task-by-task.

**Goal:** Replace the current single-route Discord↔tmux bridge with one process that serves multiple independent bridge routes from a local-only hot-reloadable JSON config.

**Architecture:** Keep the existing tmux adapter, controller, and Discord client approach, but lift them into a route-aware runtime that maintains one controller and one state store per configured route. Split global config from local route config, use `bridges.local.json` for private route data, and hot-reload route definitions by watching config file modification time while preserving active work.

**Tech Stack:** Python 3.10+, `discord.py`, `pytest`, tmux, JSON config/state files, systemd user services

---

### Task 1: Add route-aware config models and privacy-safe file loading

**Files:**
- Modify: `src/discord_codex_bridge/config.py`
- Modify: `src/discord_codex_bridge/models.py`
- Create: `bridges.example.json`
- Modify: `.env.example`
- Modify: `.gitignore`
- Test: `tests/test_runtime_helpers.py`

**Step 1: Write the failing test**

```python
def test_loads_multiple_bridge_routes_from_local_json(tmp_path):
    route_file = tmp_path / "bridges.local.json"
    route_file.write_text(
        json.dumps(
            {
                "defaults": {"tmux_window": 0, "tmux_pane": 0},
                "bridges": [
                    {"name": "alpha", "enabled": True, "channel_id": 111, "tmux_session": "session_alpha", "state_path": "./state/a.json"},
                    {"name": "beta", "enabled": True, "channel_id": 222, "tmux_session": "session_beta", "state_path": "./state/b.json"},
                ],
            }
        )
    )

    settings = Settings.from_env(
        {"DISCORD_BOT_TOKEN": "token", "BRIDGES_CONFIG_PATH": str(route_file)},
        base_dir=tmp_path,
    )

    routes = load_bridge_routes(settings)

    assert [route.name for route in routes] == ["alpha", "beta"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime_helpers.py::test_loads_multiple_bridge_routes_from_local_json -q`
Expected: FAIL because multi-route config loading does not exist yet.

**Step 3: Write minimal implementation**

Add route config dataclasses and loaders that:
- separate global settings from route definitions
- read `BRIDGES_CONFIG_PATH` from env with a repo-safe default
- validate required fields such as `name`, `channel_id`, `tmux_session`, and `state_path`
- ignore disabled routes
- support global defaults merged into each route
- keep private runtime values out of repository examples

Also update `.gitignore` to ignore `.env.*` and `bridges.local.json`, and add a repo-safe `bridges.example.json`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_runtime_helpers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discord_codex_bridge/config.py src/discord_codex_bridge/models.py bridges.example.json .env.example .gitignore tests/test_runtime_helpers.py
git commit -m "feat: add multi-bridge config loading"
```

### Task 2: Split state persistence by route runtime

**Files:**
- Modify: `src/discord_codex_bridge/state.py`
- Modify: `src/discord_codex_bridge/models.py`
- Test: `tests/test_controller.py`
- Test: `tests/test_service_helpers.py`

**Step 1: Write the failing test**

```python
def test_state_store_keeps_routes_independent(tmp_path):
    alpha_store = JsonStateStore(tmp_path / "alpha.json")
    beta_store = JsonStateStore(tmp_path / "beta.json")

    alpha_store.save(BridgeState(active=alpha_active))
    beta_store.save(BridgeState(queue=[beta_request]))

    assert alpha_store.load().active.request_id == alpha_active.request_id
    assert beta_store.load().queue[0].request_id == beta_request.request_id
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_controller.py::test_state_store_keeps_routes_independent -q`
Expected: FAIL because current tests do not cover route-scoped persistence assumptions.

**Step 3: Write minimal implementation**

Keep `JsonStateStore` simple, but add any route metadata or helper APIs needed by the service layer to construct one store per route cleanly. Avoid introducing a global shared state file.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_controller.py tests/test_service_helpers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discord_codex_bridge/state.py src/discord_codex_bridge/models.py tests/test_controller.py tests/test_service_helpers.py
git commit -m "feat: support route-scoped bridge state"
```

### Task 3: Introduce route runtime objects and multi-route dispatch

**Files:**
- Modify: `src/discord_codex_bridge/service.py`
- Modify: `src/discord_codex_bridge/models.py`
- Test: `tests/test_service_runtime_commands.py`
- Test: `tests/test_service_helpers.py`

**Step 1: Write the failing test**

```python
def test_messages_dispatch_to_matching_route_only(service, alpha_message, beta_message):
    service.load_routes([
        alpha_route,
        beta_route,
    ])

    service.handle_message(alpha_message)

    assert service.route_runtime(alpha_route.channel_id).state.active is not None
    assert service.route_runtime(beta_route.channel_id).state.active is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_helpers.py::test_messages_dispatch_to_matching_route_only -q`
Expected: FAIL because the runtime still assumes one configured channel.

**Step 3: Write minimal implementation**

Refactor the service to:
- build a `channel_id -> BridgeRuntime` map
- ignore unknown channels
- keep one controller and one state store per route
- send route effects only to the matching channel
- preserve the existing shortcut behavior within each route scope

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_service_helpers.py tests/test_service_runtime_commands.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discord_codex_bridge/service.py src/discord_codex_bridge/models.py tests/test_service_helpers.py tests/test_service_runtime_commands.py
git commit -m "feat: add multi-route bridge runtime"
```

### Task 4: Add independent per-route observation and progress cadence

**Files:**
- Modify: `src/discord_codex_bridge/service.py`
- Modify: `src/discord_codex_bridge/controller.py`
- Test: `tests/test_controller.py`
- Test: `tests/test_service_runtime_commands.py`

**Step 1: Write the failing test**

```python
def test_busy_route_does_not_block_other_route(service, now):
    service.load_routes([alpha_route, beta_route])
    service.route_runtime(alpha_route.channel_id).state.active = alpha_active

    effects = service.submit_to_route(beta_route.channel_id, beta_request, now=now)

    assert any(effect.kind == "dispatch" for effect in effects)
    assert service.route_runtime(beta_route.channel_id).state.active.request_id == beta_request.request_id
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_runtime_commands.py::test_busy_route_does_not_block_other_route -q`
Expected: FAIL because the service loop still behaves as one bridge.

**Step 3: Write minimal implementation**

Update the periodic observer so each route independently:
- checks tmux running state
- emits progress on its own cadence
- dispatches queued work when its own active task completes

Do not add a global scheduler.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_controller.py tests/test_service_runtime_commands.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discord_codex_bridge/service.py src/discord_codex_bridge/controller.py tests/test_controller.py tests/test_service_runtime_commands.py
git commit -m "feat: isolate multi-route progress and completion loops"
```

### Task 5: Add hot reload with last-known-good config behavior

**Files:**
- Modify: `src/discord_codex_bridge/service.py`
- Modify: `src/discord_codex_bridge/config.py`
- Test: `tests/test_service_helpers.py`
- Test: `tests/test_runtime_helpers.py`

**Step 1: Write the failing test**

```python
def test_hot_reload_adds_new_route_without_dropping_running_route(service, tmp_path):
    write_routes(tmp_path, [alpha_route])
    service.load_from_disk()
    service.route_runtime(alpha_route.channel_id).state.active = alpha_active

    write_routes(tmp_path, [alpha_route, beta_route])
    service.reload_if_config_changed()

    assert alpha_route.channel_id in service.routes_by_channel
    assert beta_route.channel_id in service.routes_by_channel
    assert service.route_runtime(alpha_route.channel_id).state.active.request_id == alpha_active.request_id
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_helpers.py::test_hot_reload_adds_new_route_without_dropping_running_route -q`
Expected: FAIL because config reload does not exist yet.

**Step 3: Write minimal implementation**

Implement mtime-based reload that:
- reloads only on file change
- diffs added, removed, and updated routes
- keeps the last known-good config if reload parsing fails
- drains disabled/removed routes instead of dropping active work immediately

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_service_helpers.py tests/test_runtime_helpers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discord_codex_bridge/service.py src/discord_codex_bridge/config.py tests/test_service_helpers.py tests/test_runtime_helpers.py
git commit -m "feat: hot reload multi-bridge routes"
```

### Task 6: Replace single-route CLI/docs/systemd surface

**Files:**
- Modify: `src/discord_codex_bridge/__main__.py`
- Modify: `README.md`
- Create: `systemd/discord-codex-multi-bridge.service`
- Test: `tests/test_runtime_helpers.py`

**Step 1: Write the failing test**

```python
def test_main_uses_local_route_file_by_default(tmp_path):
    env = {
        "DISCORD_BOT_TOKEN": "token",
        "BRIDGES_CONFIG_PATH": str(tmp_path / "bridges.local.json"),
    }
    settings = Settings.from_env(env, base_dir=tmp_path)
    assert settings.bridges_config_path.name == "bridges.local.json"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime_helpers.py::test_main_uses_local_route_file_by_default -q`
Expected: FAIL because the CLI and settings still assume one route file model.

**Step 3: Write minimal implementation**

Update the entrypoint and docs so operators:
- keep secrets in `.env`
- keep real route mappings in `bridges.local.json`
- run one systemd user unit for all bridges
- stop using one unit per route

Document direct replacement of the old services after verification.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_runtime_helpers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discord_codex_bridge/__main__.py README.md systemd/discord-codex-multi-bridge.service tests/test_runtime_helpers.py
git commit -m "feat: add multi-bridge runtime entrypoint and docs"
```

### Task 7: End-to-end regression validation

**Files:**
- Verify only: `tests/`
- Verify only: `systemd/discord-codex-multi-bridge.service`
- Verify only: `bridges.example.json`

**Step 1: Run targeted tests first**

Run: `pytest tests/test_runtime_helpers.py tests/test_service_helpers.py tests/test_service_runtime_commands.py -q`
Expected: PASS

**Step 2: Run full test suite**

Run: `pytest -q`
Expected: PASS

**Step 3: Verify repository privacy rules**

Run:

```bash
git status --short
rg -n "DISCORD_BOT_TOKEN|w_evolution|1479985018565820488" .
```

Expected:
- no real token or local runtime route values appear in tracked files
- local-only files remain ignored

**Step 4: Commit**

```bash
git add .
git commit -m "feat: replace single bridge runtime with multi-bridge service"
```
