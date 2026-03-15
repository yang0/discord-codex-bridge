from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from discord_codex_bridge.models import BridgeRouteConfig, WezTermTargetConfig


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    tmux_bin: str
    tmux_window: int
    tmux_pane: int
    check_interval_sec: int
    progress_interval_sec: int
    progress_capture_lines: int
    completion_lines: int
    bridges_config_path: Path
    terminal_backend: str = "auto"
    wezterm_bin: str = "wezterm"

    @classmethod
    def from_env(cls, env: MutableMapping[str, str], *, base_dir: Path) -> "Settings":
        token = env.get("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN is required")

        bridges_config_path = Path(env.get("BRIDGES_CONFIG_PATH", "./bridges.local.json")).expanduser()
        if not bridges_config_path.is_absolute():
            bridges_config_path = (base_dir / bridges_config_path).resolve()

        return cls(
            discord_bot_token=token,
            tmux_bin=_resolve_tmux_bin(env),
            tmux_window=int(env.get("TMUX_WINDOW", "0")),
            tmux_pane=int(env.get("TMUX_PANE", "0")),
            check_interval_sec=int(env.get("CHECK_INTERVAL_SEC", "5")),
            progress_interval_sec=int(env.get("PROGRESS_INTERVAL_SEC", "300")),
            progress_capture_lines=int(env.get("PROGRESS_CAPTURE_LINES", "220")),
            completion_lines=int(env.get("COMPLETION_LINES", "100")),
            bridges_config_path=bridges_config_path,
            terminal_backend=env.get("TERMINAL_BACKEND", "auto").strip().lower() or "auto",
            wezterm_bin=_resolve_wezterm_bin(env),
        )

    def resolved_terminal_backend(self, *, platform: str | None = None) -> str:
        return resolve_terminal_backend_name(self.terminal_backend, platform=platform)


def load_env_file(path: Path, env: MutableMapping[str, str] | None = None) -> MutableMapping[str, str]:
    target = env if env is not None else os.environ
    if not path.exists():
        return target

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        target.setdefault(key, value)
    return target


def load_bridge_routes(settings: Settings) -> list[BridgeRouteConfig]:
    path = settings.bridges_config_path
    if not path.exists():
        raise FileNotFoundError(f"Bridge config file not found: {path}")

    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Bridge config must be a JSON object")

    defaults_payload = payload.get("defaults", {})
    if defaults_payload is None:
        defaults_payload = {}
    if not isinstance(defaults_payload, dict):
        raise ValueError("Bridge config field 'defaults' must be an object")

    bridges_payload = payload.get("bridges", [])
    if not isinstance(bridges_payload, list):
        raise ValueError("Bridge config field 'bridges' must be a list")

    routes: list[BridgeRouteConfig] = []
    seen_names: set[str] = set()
    seen_channels: set[int] = set()
    for index, raw_route in enumerate(bridges_payload):
        if not isinstance(raw_route, dict):
            raise ValueError(f"Bridge entry at index {index} must be an object")

        if raw_route.get("enabled", True) is False:
            continue

        merged = {
            "tmux_window": settings.tmux_window,
            "tmux_pane": settings.tmux_pane,
            "check_interval_sec": settings.check_interval_sec,
            "progress_interval_sec": settings.progress_interval_sec,
            "progress_capture_lines": settings.progress_capture_lines,
            "completion_lines": settings.completion_lines,
        }
        merged.update(defaults_payload)
        merged.update(raw_route)
        terminal_target = _load_wezterm_target(merged, index=index)
        tmux_session = str(merged.get("tmux_session", "")).strip()
        if not tmux_session and terminal_target is None:
            raise ValueError(
                f"Bridge entry at index {index} requires either non-empty 'tmux_session' or 'terminal_target'"
            )

        route = BridgeRouteConfig(
            name=_require_non_empty_string(merged, "name", index=index),
            channel_id=_require_int(merged, "channel_id", index=index),
            state_path=_resolve_path(
                _require_non_empty_string(merged, "state_path", index=index),
                base_dir=path.parent,
            ),
            check_interval_sec=_require_int(merged, "check_interval_sec", index=index),
            progress_interval_sec=_require_int(merged, "progress_interval_sec", index=index),
            progress_capture_lines=_require_int(merged, "progress_capture_lines", index=index),
            completion_lines=_require_int(merged, "completion_lines", index=index),
            enabled=bool(merged.get("enabled", True)),
            tmux_session=tmux_session,
            tmux_window=_require_int(merged, "tmux_window", index=index),
            tmux_pane=_require_int(merged, "tmux_pane", index=index),
            terminal_target=terminal_target,
        )

        if route.name in seen_names:
            raise ValueError(f"Duplicate bridge name: {route.name}")
        if route.channel_id in seen_channels:
            raise ValueError(f"Duplicate bridge channel_id: {route.channel_id}")
        seen_names.add(route.name)
        seen_channels.add(route.channel_id)
        routes.append(route)

    return routes


def _resolve_tmux_bin(env: MutableMapping[str, str]) -> str:
    explicit = env.get("TMUX_BIN", "").strip()
    if explicit:
        return explicit

    discovered = shutil.which("tmux")
    if discovered:
        return discovered

    fallback = Path.home() / ".local/bin/tmux"
    if fallback.exists():
        return str(fallback)

    return "tmux"


def _resolve_wezterm_bin(env: MutableMapping[str, str]) -> str:
    explicit = env.get("WEZTERM_BIN", "").strip()
    if explicit:
        return explicit

    discovered = shutil.which("wezterm")
    if discovered:
        return discovered

    discovered = shutil.which("wezterm.exe")
    if discovered:
        return discovered

    return "wezterm"


def resolve_terminal_backend_name(configured: str, *, platform: str | None = None) -> str:
    value = configured.strip().lower()
    if value in {"tmux", "wezterm"}:
        return value
    if value != "auto":
        raise ValueError(f"Unsupported TERMINAL_BACKEND: {configured}")
    current_platform = sys.platform if platform is None else platform
    return "wezterm" if current_platform.startswith("win") else "tmux"


def _require_non_empty_string(payload: Mapping[str, Any], key: str, *, index: int) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"Bridge entry at index {index} requires non-empty '{key}'")
    return value


def _require_int(payload: Mapping[str, Any], key: str, *, index: int) -> int:
    value = payload.get(key)
    if value is None or value == "":
        raise ValueError(f"Bridge entry at index {index} requires '{key}'")
    return int(value)


def _resolve_path(raw_path: str, *, base_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def _load_wezterm_target(payload: Mapping[str, Any], *, index: int) -> WezTermTargetConfig | None:
    raw_target = payload.get("terminal_target")
    if raw_target is None:
        return None
    if not isinstance(raw_target, dict):
        raise ValueError(f"Bridge entry at index {index} field 'terminal_target' must be an object")
    workspace = str(raw_target.get("workspace", "")).strip()
    if not workspace:
        raise ValueError(f"Bridge entry at index {index} requires non-empty 'terminal_target.workspace'")
    pane_title = _normalize_optional_string(raw_target.get("pane_title"))
    pane_title_regex = _normalize_optional_string(raw_target.get("pane_title_regex"))
    cwd_contains = _normalize_optional_string(raw_target.get("cwd_contains"))
    return WezTermTargetConfig(
        workspace=workspace,
        pane_title=pane_title,
        pane_title_regex=pane_title_regex,
        cwd_contains=cwd_contains,
    )


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
