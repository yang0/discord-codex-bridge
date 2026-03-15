# WezTermBackend Cross-Platform Design

## Context

`discord-codex-bridge` currently assumes Linux because the runtime control plane is hard-wired to `tmux`. The bridge logic itself is mostly platform-neutral, but the terminal integration layer, route schema, and deployment docs are tmux/Linux-specific.

The goal of this design is to preserve current Linux behavior while making the application run on both Linux and Windows:

- Linux keeps using `tmux`
- Windows uses `WezTerm`
- one bridge process uses one backend at a time in phase 1
- same-process mixed backends are explicitly out of scope for phase 1

## Goals

- Keep current Linux behavior working with minimal disruption
- Add a backend abstraction so the service no longer depends on tmux-specific types
- Support Windows through `wezterm cli`
- Preserve existing route semantics where the bridge attaches to an already-running interactive Codex session
- Keep the `ai`, `f`, `p`, `e`, `q`, `qx`, and `i` shortcut behaviors aligned across platforms whenever feasible

## Non-Goals

- No mixed backend routing in the same process
- No Windows Terminal UI automation
- No redesign where the bridge owns and launches Codex sessions directly
- No breaking change to existing Linux route config in phase 1

## Recommended Approach

Phase 1 introduces a generic terminal backend interface and keeps backend selection global per process:

- `tmux` remains the Linux backend
- `wezterm` becomes the Windows backend
- backend selection is driven by a new `TERMINAL_BACKEND=auto|tmux|wezterm` setting
- `auto` resolves to `tmux` on Linux and `wezterm` on Windows

The service layer only depends on a shared backend protocol:

- resolve a configured route target into an operational target
- capture recent output text
- send message text
- send interrupt
- resolve current working directory

## Architecture

### 1. Shared Backend Contract

Add a backend-neutral module that defines:

- `TerminalDispatchResult`
- `TerminalRouteTarget`
- `ResolvedTerminalTarget`
- `TerminalBackend`

The service should use this interface instead of calling `TmuxBridge` directly.

### 2. Tmux Backend Preservation

Wrap the current tmux integration behind the new contract.

This is intentionally not a rewrite. The existing tmux logic should mostly move behind the new interface so Linux behavior and tests remain stable.

### 3. WezTerm Backend

Implement a `WezTermBackend` around `wezterm cli`.

Primary operations:

- `wezterm cli list --format json`
- `wezterm cli get-text --pane-id <id>`
- `wezterm cli send-text --pane-id <id> ...`

The backend will resolve a configured route selector to exactly one live pane before any operation.

### 4. Route Target Model

Keep existing Linux route fields:

- `tmux_session`
- `tmux_window`
- `tmux_pane`

Add a backend-neutral wrapper in the route model:

- global backend selection still decides which target shape is valid
- Linux routes continue to use legacy tmux fields
- WezTerm routes use a new `terminal_target` object

Proposed WezTerm selector fields for phase 1:

- `workspace` required
- `pane_title` optional exact title
- `pane_title_regex` optional regex
- `cwd_contains` optional path substring hint

Selector resolution rules:

1. filter by workspace
2. apply exact title filter if present
3. apply title regex if present
4. apply cwd substring if present
5. require exactly one match

Multiple matches are configuration errors. Zero matches are runtime resolution errors.

### 5. Interrupt Behavior

Current tmux interrupt behavior sends the `Escape` key.

WezTerm interrupt support must be isolated behind backend behavior instead of leaking assumptions into the service. Phase 1 should support one of these, in priority order:

1. documented raw escape input through `wezterm cli send-text`
2. backend-specific fallback that reliably produces the same effect
3. explicit unsupported-path error with a user-visible message

The critical requirement is that lack of an interrupt path must not block the rest of Windows support.

### 6. Working Directory Resolution

`ai` shortcut support currently depends on the target pane working directory.

For tmux this continues through `#{pane_current_path}`.
For WezTerm the backend should read `cwd` from `wezterm cli list --format json`.

If cwd resolution fails:

- normal message dispatch still works
- `ai` shortcut degrades gracefully with no workspace root

### 7. Deployment Surface

Linux docs remain tmux-oriented.
Windows docs should explain:

- required `WezTerm` installation
- `TERMINAL_BACKEND=wezterm` or `auto`
- route selector format for WezTerm
- a Windows startup method such as Task Scheduler

## Error Handling

- backend selection invalid for current OS: fail startup loudly
- selector ambiguity: per-route runtime error, no cross-route crash
- selector not found: per-route runtime error, monitor retries later
- cwd lookup failure: degrade only the `ai` path
- interrupt unsupported: return explicit runtime message

## Testing Strategy

### Existing Baseline

There is already a Windows-sensitive failing test around workspace path normalization. That should be fixed as part of this work so the suite becomes truly cross-platform.

### New Coverage

- backend auto-selection by OS
- route config loading for tmux and WezTerm shapes
- WezTerm selector resolution behavior
- service compatibility with backend abstraction
- `ai` path behavior with generic backend cwd lookup
- interrupt behavior for supported and unsupported backend cases

## Delivery Slices

### Slice 1

- backend interface
- tmux adapter migration
- no behavior change on Linux

### Slice 2

- config model changes
- backend auto-selection
- fix current Windows path test fragility

### Slice 3

- WezTerm backend implementation
- unit tests for selector resolution and CLI wrappers

### Slice 4

- docs, examples, Windows runbook updates
- full verification

## Why This Design

This keeps the current product model intact:

- bridge still attaches to long-lived interactive Codex sessions
- Linux users keep their tmux workflow
- Windows gets a documented backend with a real external control surface

It also leaves a clean upgrade path for a future mixed-backend runtime if that ever becomes necessary.
