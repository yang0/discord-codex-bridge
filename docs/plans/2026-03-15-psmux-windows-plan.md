# Windows Psmux Implementation Plan

> **Execution Skill:** Use `superpowers:subagent-driven-development` (same session) or `superpowers:executing-plans` (separate session) to implement this plan task-by-task.

**Goal:** Make Windows prefer `psmux` through the existing tmux-style backend while preserving explicit `wezterm` support.

**Architecture:** Keep `WezTermBackend` available for explicit use, but move Windows `auto` resolution onto `TmuxTerminalBackend`. Patch `TmuxBridge` to accept `psmux`'s unformatted `list-sessions` output and its stricter `capture-pane` flag parsing.

**Tech Stack:** Python 3.11, pytest, PowerShell, `psmux`

---

### Task 1: Lock Down TmuxBridge Compatibility

**Files:**
- Modify: `tests/test_tmux_bridge.py`
- Modify: `src/discord_codex_bridge/tmux_bridge.py`

**Step 1: Write the failing test**

- Add one test proving `TmuxBridge.list_sessions()` can parse plain `psmux` `list-sessions` output without tab-separated format fields.
- Add one test proving `TmuxBridge.capture_tail()` calls `capture-pane` with `-p -t` as separate arguments.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tmux_bridge.py -q`

Expected: FAIL because the current implementation requires tab-separated fields and uses `-pt`.

**Step 3: Write minimal implementation**

- Add an injectable runner to `TmuxBridge` for testability.
- Parse tmux formatted output when tabs exist.
- Fall back to parsing plain `psmux` session lines when tabs are absent.
- Split `capture-pane` flags into `-p`, `-t`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_tmux_bridge.py -q`

Expected: PASS

### Task 2: Switch Windows Auto Backend To Tmux/Psmux

**Files:**
- Modify: `tests/test_runtime_helpers.py`
- Modify: `src/discord_codex_bridge/config.py`
- Modify: `src/discord_codex_bridge/backend_factory.py`

**Step 1: Write the failing test**

- Update Windows auto-backend tests to expect `tmux` / `TmuxTerminalBackend`.
- Add a test showing Windows `TMUX_BIN` discovery can prefer `psmux` when available.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime_helpers.py -q`

Expected: FAIL because Windows auto currently resolves to `wezterm`.

**Step 3: Write minimal implementation**

- Resolve Windows `auto` to `tmux`.
- Prefer `psmux` / `tmux` discovery on Windows for `TMUX_BIN`.
- Keep explicit `wezterm` resolution intact.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_runtime_helpers.py -q`

Expected: PASS

### Task 3: Update Docs And Examples

**Files:**
- Modify: `README.md`
- Modify: `bridges.example.json`

**Step 1: Update minimal docs**

- Replace the Windows recommended path with `psmux` + `tmux_session`.
- Keep a short note that explicit `wezterm` remains available for legacy setups.

**Step 2: Verify docs stay aligned**

Run: `pytest -q`

Expected: PASS

### Task 4: Run Real Windows Smoke Test

**Files:**
- No tracked file changes required

**Step 1: Start a real attached `psmux` session**

Use `tmux new-session -A -s <session-name>` in a separate Windows console.

**Step 2: Validate bridge command set**

- `list-sessions`
- `display-message`
- `send-keys`
- `capture-pane`

**Step 3: Validate through Python backend**

Use `TmuxBridge` or `TmuxTerminalBackend` against the live session and confirm target resolution, current path, text injection, and tail capture.

**Step 4: Final verification**

Run:

- `pytest tests/test_tmux_bridge.py tests/test_runtime_helpers.py -q`
- `pytest -q`

Expected: PASS
