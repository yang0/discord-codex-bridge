from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from discord_codex_bridge.models import BridgeRouteConfig, WezTermTargetConfig
from discord_codex_bridge.tmux_bridge import RUNNING_MARKER, pane_indicates_running
from discord_codex_bridge.terminal_backend import TerminalDispatchResult


@dataclass(frozen=True)
class WezTermPane:
    pane_id: str
    workspace: str
    title: str
    cwd: str


class WezTermBackend:
    def __init__(
        self,
        *,
        wezterm_bin: str = "wezterm",
        runner: Callable[[list[str]], str] | None = None,
    ) -> None:
        self.wezterm_bin = wezterm_bin
        self.runner = runner or self._run_subprocess

    def resolve_target(self, route: BridgeRouteConfig) -> str:
        selector = _require_terminal_target(route)
        matches = self._matching_panes(selector)
        if not matches:
            raise ValueError(f"Unable to resolve WezTerm pane for route '{route.name}'")
        if len(matches) > 1:
            raise ValueError(f"Route '{route.name}' matched multiple WezTerm panes")
        return matches[0].pane_id

    def capture_tail(self, target: str, *, lines: int) -> str:
        return self._run("cli", "get-text", "--pane-id", target, "--start-line", f"-{lines}")

    def send_message(self, route: BridgeRouteConfig, message: str) -> TerminalDispatchResult:
        target = self.resolve_target(route)
        self._run("cli", "send-text", "--pane-id", target, "--no-paste", f"{message}\n")
        tail = self.capture_tail(target, lines=20)
        return TerminalDispatchResult(target=target, tail=tail, running=self._tail_indicates_running(tail))

    def send_interrupt(self, route: BridgeRouteConfig) -> TerminalDispatchResult:
        target = self.resolve_target(route)
        self._run("cli", "send-text", "--pane-id", target, "--no-paste", "\x1b")
        tail = self.capture_tail(target, lines=20)
        return TerminalDispatchResult(target=target, tail=tail, running=self._tail_indicates_running(tail))

    def get_current_path(self, route: BridgeRouteConfig) -> str:
        selector = _require_terminal_target(route)
        matches = self._matching_panes(selector)
        if not matches:
            raise ValueError(f"Unable to resolve WezTerm pane for route '{route.name}'")
        if len(matches) > 1:
            raise ValueError(f"Route '{route.name}' matched multiple WezTerm panes")
        return matches[0].cwd

    def _matching_panes(self, selector: WezTermTargetConfig) -> list[WezTermPane]:
        panes = self._list_panes()
        matches = [pane for pane in panes if pane.workspace == selector.workspace]
        if selector.pane_title is not None:
            matches = [pane for pane in matches if pane.title == selector.pane_title]
        if selector.pane_title_regex is not None:
            pattern = re.compile(selector.pane_title_regex)
            matches = [pane for pane in matches if pattern.search(pane.title)]
        if selector.cwd_contains is not None:
            matches = [pane for pane in matches if selector.cwd_contains in pane.cwd]
        return matches

    def _list_panes(self) -> list[WezTermPane]:
        payload = json.loads(self._run("cli", "list", "--format", "json"))
        if not isinstance(payload, list):
            raise ValueError("wezterm cli list did not return a JSON array")
        panes: list[WezTermPane] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            panes.append(
                WezTermPane(
                    pane_id=str(item.get("pane_id", "")).strip(),
                    workspace=str(item.get("workspace", "")).strip(),
                    title=str(item.get("title", "")).strip(),
                    cwd=_normalize_cwd(item.get("cwd")),
                )
            )
        return panes

    def _run(self, *args: str) -> str:
        return self.runner([self.wezterm_bin, *args])

    def _run_subprocess(self, args: list[str]) -> str:
        completed = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout

    def _tail_indicates_running(self, tail: str) -> bool:
        return RUNNING_MARKER in tail or pane_indicates_running(tail)


def _require_terminal_target(route: BridgeRouteConfig) -> WezTermTargetConfig:
    if route.terminal_target is None:
        raise ValueError(f"Route '{route.name}' does not define a WezTerm terminal_target")
    return route.terminal_target


def _normalize_cwd(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme != "file":
        return raw
    path = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:", path):
        return path[1:]
    return path or raw
