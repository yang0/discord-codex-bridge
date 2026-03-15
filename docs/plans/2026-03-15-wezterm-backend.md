# WezTermBackend Cross-Platform Implementation Plan

> **Execution Skill:** Use `superpowers:subagent-driven-development` (same session) or `superpowers:executing-plans` (separate session) to implement this plan task-by-task.

**Goal:** Refactor `discord-codex-bridge` into a cross-platform bridge that keeps Linux `tmux` support and adds Windows `WezTerm` support through a shared terminal backend abstraction.

**Architecture:** Introduce a backend-neutral terminal control contract, move current tmux behavior behind that contract, add global backend selection plus WezTerm route selectors, then implement a `WezTermBackend` using `wezterm cli` while preserving service/controller behavior.

**Tech Stack:** Python 3.10+, `pytest`, `discord.py`, `tmux`, `wezterm cli`

---

### Task 1: Write failing tests for backend selection and generic route loading

**Files:**
- Modify: `tests/test_runtime_helpers.py`
- Modify: `src/discord_codex_bridge/config.py`
- Modify: `src/discord_codex_bridge/models.py`

**Step 1: Write the failing test**

Add tests that describe:

- `Settings.from_env(..., base_dir=...)` defaults `terminal_backend` to `auto`
- `auto` resolves to `tmux` on Linux
- explicit `TERMINAL_BACKEND=wezterm` is preserved
- route loader accepts a WezTerm `terminal_target` object when backend is `wezterm`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime_helpers.py -q`
Expected: FAIL because config/model code does not yet expose terminal backend or WezTerm route targets.

**Step 3: Write minimal implementation**

Implement only enough config/model changes to satisfy the new tests:

- add backend setting fields
- add route target representation
- keep tmux compatibility

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_runtime_helpers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_helpers.py src/discord_codex_bridge/config.py src/discord_codex_bridge/models.py
git commit -m "feat: add terminal backend config model"
```

### Task 2: Write failing tests for a backend-neutral service contract

**Files:**
- Modify: `tests/test_service_runtime_commands.py`
- Modify: `tests/test_service_helpers.py`
- Create: `src/discord_codex_bridge/terminal_backend.py`
- Modify: `src/discord_codex_bridge/service.py`
- Modify: `src/discord_codex_bridge/tmux_bridge.py`

**Step 1: Write the failing test**

Add tests proving the service can work with a generic backend fake instead of a tmux-specific fake:

- dispatch uses a resolved backend target
- fetch uses generic `capture_tail`
- AI cwd resolution uses generic backend lookup
- interrupt path goes through backend abstraction

Also update the existing Windows path-sensitive AI workspace test so it asserts platform-stable behavior instead of a Unix-only `Path('/tmp/workspace')` literal.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_runtime_commands.py tests/test_service_helpers.py -q`
Expected: FAIL because service still expects tmux-specific method signatures and path behavior.

**Step 3: Write minimal implementation**

Introduce a backend protocol and adapt the service to use it. Keep `TmuxBridge` behavior intact by making it satisfy the new contract, directly or through a small adapter.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_service_runtime_commands.py tests/test_service_helpers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_service_runtime_commands.py tests/test_service_helpers.py src/discord_codex_bridge/terminal_backend.py src/discord_codex_bridge/service.py src/discord_codex_bridge/tmux_bridge.py
git commit -m "refactor: move service onto terminal backend interface"
```

### Task 3: Write failing tests for WezTerm selector resolution and CLI wrappers

**Files:**
- Create: `tests/test_wezterm_backend.py`
- Create: `src/discord_codex_bridge/wezterm_backend.py`

**Step 1: Write the failing test**

Add tests for:

- resolving a pane by workspace + exact title
- resolving a pane by workspace + regex
- rejecting zero matches
- rejecting multiple matches
- reading pane cwd from `list`
- capturing pane output through `get-text`
- sending text through `send-text`

Use subprocess stubs/fakes instead of requiring a real WezTerm process.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wezterm_backend.py -q`
Expected: FAIL because `wezterm_backend.py` does not exist yet.

**Step 3: Write minimal implementation**

Implement selector parsing, pane resolution, CLI invocation, and dispatch helpers.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wezterm_backend.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_wezterm_backend.py src/discord_codex_bridge/wezterm_backend.py
git commit -m "feat: add wezterm terminal backend"
```

### Task 4: Write failing tests for backend factory and app wiring

**Files:**
- Modify: `tests/test_runtime_helpers.py`
- Modify: `src/discord_codex_bridge/__main__.py`
- Modify: `src/discord_codex_bridge/config.py`
- Modify: `src/discord_codex_bridge/service.py`

**Step 1: Write the failing test**

Add tests that prove:

- backend `auto` resolves correctly for the current platform
- explicit `tmux` / `wezterm` produce the right backend instance
- unsupported backend selection fails clearly

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_runtime_helpers.py -q`
Expected: FAIL because no backend factory exists yet.

**Step 3: Write minimal implementation**

Add a backend factory and wire it into app startup and service construction.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_runtime_helpers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_runtime_helpers.py src/discord_codex_bridge/__main__.py src/discord_codex_bridge/config.py src/discord_codex_bridge/service.py
git commit -m "feat: wire backend selection into startup"
```

### Task 5: Document Linux and Windows setup paths

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `bridges.example.json`

**Step 1: Write the failing documentation check**

Create a short checklist in your working notes and verify the docs are missing:

- `TERMINAL_BACKEND`
- Windows `WezTerm` requirements
- WezTerm route selector examples
- Linux compatibility note

**Step 2: Update documentation**

Document:

- backend selection
- Linux `tmux` path
- Windows `WezTerm` path
- sample WezTerm route entries
- known interrupt caveat if still applicable

**Step 3: Run relevant tests**

Run: `pytest tests/test_runtime_helpers.py tests/test_service_runtime_commands.py tests/test_wezterm_backend.py -q`
Expected: PASS

**Step 4: Commit**

```bash
git add README.md .env.example bridges.example.json
git commit -m "docs: describe cross-platform terminal backends"
```

### Task 6: Full verification and branch completion

**Files:**
- Verify only

**Step 1: Run the full test suite**

Run: `pytest -q`
Expected: PASS with zero failures.

**Step 2: Inspect git status**

Run: `git status --short`
Expected: clean working tree.

**Step 3: Push the branch**

Run: `git push -u origin issue-20-wezterm-backend`
Expected: branch published.

**Step 4: Merge to main after verification**

Run:

```bash
git checkout main
git pull --ff-only
git merge --ff-only issue-20-wezterm-backend
git push origin main
```

Expected: `main` contains the verified cross-platform backend work.
