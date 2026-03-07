# Discord Codex Bridge Implementation Plan

> **Execution Skill:** Use `superpowers:subagent-driven-development` (same session) or `superpowers:executing-plans` (separate session) to implement this plan task-by-task.

**Goal:** Build an independent backend service that bridges one Discord channel to the `oc_backup` tmux Codex pane, checks completion every minute, and reports progress every five minutes.

**Architecture:** Use a small Python package with a pure controller for queueing and cadence decisions, a tmux adapter for reliable target resolution and pane capture, and a Discord runtime that only depends on a bot token and channel id. Persist active task and queue to a local JSON state file so the bridge can resume after restarts without depending on OpenClaw.

**Tech Stack:** Python 3.11+, `discord.py`, `pytest`, tmux, systemd (sample unit)

---

### Task 1: Project Skeleton And Red Tests

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `tests/test_tmux_bridge.py`
- Create: `tests/test_controller.py`

**Step 1: Write the failing test**

```python
def test_resolve_tmux_target_uses_session_group_when_exact_session_missing():
    sessions = [
        SessionRef(name="bridge-2", group="bridge", attached=1, last_attached=10),
    ]
    assert resolve_target("bridge", 0, 0, sessions) == "bridge-2:0.0"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tmux_bridge.py -q`
Expected: FAIL because `discord_codex_bridge.tmux_bridge` is missing.

**Step 3: Write minimal implementation**

Create the package modules and minimal dataclasses/functions needed for imports.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_tmux_bridge.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml tests/test_tmux_bridge.py tests/test_controller.py src/discord_codex_bridge
git commit -m "feat: add discord codex bridge core"
```

### Task 2: Controller And State Persistence

**Files:**
- Create: `src/discord_codex_bridge/models.py`
- Create: `src/discord_codex_bridge/controller.py`
- Create: `src/discord_codex_bridge/state.py`
- Test: `tests/test_controller.py`

**Step 1: Write the failing test**

```python
def test_tick_completion_dispatches_next_queued_request():
    controller = BridgeController(progress_interval_sec=300)
    controller.submit(first_request, now=t0)
    controller.submit(second_request, now=t0)

    effects = controller.observe(active_running=False, now=t0 + timedelta(minutes=6))

    assert any(effect.kind == "dispatch" for effect in effects)
    assert controller.state.active.request_id == second_request.request_id
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_controller.py::test_tick_completion_dispatches_next_queued_request -q`
Expected: FAIL because `BridgeController` behavior is not implemented.

**Step 3: Write minimal implementation**

Implement queueing, progress cadence, completion detection, and JSON state read/write.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_controller.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discord_codex_bridge/models.py src/discord_codex_bridge/controller.py src/discord_codex_bridge/state.py tests/test_controller.py
git commit -m "feat: add bridge controller and state persistence"
```

### Task 3: Runtime Glue And Docs

**Files:**
- Create: `src/discord_codex_bridge/config.py`
- Create: `src/discord_codex_bridge/summary.py`
- Create: `src/discord_codex_bridge/service.py`
- Create: `src/discord_codex_bridge/__main__.py`
- Create: `.env.example`
- Create: `README.md`
- Create: `systemd/discord-codex-bridge.service`

**Step 1: Write the failing test**

```python
def test_running_detection_uses_esc_to_interrupt_only():
    assert pane_indicates_running("... esc to interrupt ...") is True
    assert pane_indicates_running("finished") is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tmux_bridge.py::test_pane_indicates_running_uses_esc_to_interrupt_marker -q`
Expected: FAIL because the helper is not implemented.

**Step 3: Write minimal implementation**

Wire Discord client, tmux subprocess calls, progress summaries, message chunking, env loading, and sample deployment docs.

**Step 4: Run test to verify it passes**

Run: `pytest -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/discord_codex_bridge/config.py src/discord_codex_bridge/summary.py src/discord_codex_bridge/service.py src/discord_codex_bridge/__main__.py .env.example README.md systemd/discord-codex-bridge.service
git commit -m "feat: add discord codex bridge runtime"
```
