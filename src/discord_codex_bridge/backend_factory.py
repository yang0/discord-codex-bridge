from __future__ import annotations

from discord_codex_bridge.config import Settings
from discord_codex_bridge.terminal_backend import TerminalBackend
from discord_codex_bridge.tmux_bridge import TmuxTerminalBackend
from discord_codex_bridge.wezterm_backend import WezTermBackend


def create_terminal_backend(settings: Settings, *, platform: str | None = None) -> TerminalBackend:
    backend_name = settings.resolved_terminal_backend(platform=platform)
    if backend_name == "tmux":
        return TmuxTerminalBackend(tmux_bin=settings.tmux_bin)
    if backend_name == "wezterm":
        return WezTermBackend(wezterm_bin=settings.wezterm_bin)
    raise ValueError(f"Unsupported TERMINAL_BACKEND: {settings.terminal_backend}")
