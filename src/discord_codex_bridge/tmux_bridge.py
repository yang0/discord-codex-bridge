from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

from discord_codex_bridge.models import BridgeRouteConfig
from discord_codex_bridge.terminal_backend import TerminalDispatchResult


RUNNING_MARKER = "esc to interrupt"
RUNNING_PROBE_LINES = 10


@dataclass(frozen=True)
class SessionRef:
    name: str
    group: str
    attached: bool
    last_attached: int


@dataclass(frozen=True)
class DispatchResult:
    target: str
    tail: str
    running: bool


def pane_indicates_running(text: str) -> bool:
    tail = "\n".join(text.splitlines()[-RUNNING_PROBE_LINES:])
    return RUNNING_MARKER in tail


def resolve_target(requested_session: str, window: int, pane: int, sessions: list[SessionRef]) -> str:
    exact = [session for session in sessions if session.name == requested_session]
    if exact:
        return _format_target(_best_session(exact), window, pane)

    by_group = [session for session in sessions if session.group == requested_session]
    if by_group:
        return _format_target(_best_session(by_group), window, pane)

    by_prefix = [session for session in sessions if session.name.startswith(f"{requested_session}-")]
    if by_prefix:
        return _format_target(_best_session(by_prefix), window, pane)

    raise ValueError(f"Unable to resolve tmux session '{requested_session}'")


class TmuxBridge:
    def __init__(self, *, tmux_bin: str = "tmux") -> None:
        self.tmux_bin = tmux_bin

    def list_sessions(self) -> list[SessionRef]:
        output = self._run(
            "list-sessions",
            "-F",
            "#{session_name}\t#{session_group}\t#{session_attached}\t#{session_last_attached}",
        )
        sessions: list[SessionRef] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            name, group, attached, last_attached = line.split("\t")
            sessions.append(
                SessionRef(
                    name=name,
                    group="" if group == name else group,
                    attached=attached == "1",
                    last_attached=int(last_attached or 0),
                )
            )
        return sessions

    def resolve_pane_target(self, requested_session: str, window: int, pane: int) -> str:
        return resolve_target(requested_session, window, pane, self.list_sessions())

    def capture_tail(self, target: str, *, lines: int) -> str:
        return self._run("capture-pane", "-pt", target, "-S", f"-{lines}")

    def get_pane_current_path(self, requested_session: str, window: int, pane: int) -> str:
        target = self.resolve_pane_target(requested_session, window, pane)
        return self._run("display-message", "-p", "-t", target, "#{pane_current_path}").strip()

    def task_is_running(self, target: str) -> bool:
        return pane_indicates_running(self.capture_tail(target, lines=RUNNING_PROBE_LINES))

    def send_message(self, requested_session: str, window: int, pane: int, message: str) -> DispatchResult:
        target = self.resolve_pane_target(requested_session, window, pane)
        self._run("send-keys", "-t", target, "-l", "--", message)
        time.sleep(0.2)
        self._run("send-keys", "-t", target, "Enter")
        time.sleep(1.0)
        tail = self.capture_tail(target, lines=20)
        return DispatchResult(target=target, tail=tail, running=pane_indicates_running(tail))

    def send_escape(self, requested_session: str, window: int, pane: int) -> DispatchResult:
        target = self.resolve_pane_target(requested_session, window, pane)
        self._run("send-keys", "-t", target, "Escape")
        time.sleep(0.3)
        tail = self.capture_tail(target, lines=20)
        return DispatchResult(target=target, tail=tail, running=pane_indicates_running(tail))

    def _run(self, *args: str) -> str:
        completed = subprocess.run(
            [self.tmux_bin, *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout


def _best_session(sessions: list[SessionRef]) -> SessionRef:
    return sorted(sessions, key=lambda item: (item.attached, item.last_attached, item.name), reverse=True)[0]


def _format_target(session: SessionRef, window: int, pane: int) -> str:
    return f"{session.name}:{window}.{pane}"


class TmuxTerminalBackend:
    def __init__(self, *, tmux_bin: str = "tmux", tmux: TmuxBridge | None = None) -> None:
        self.tmux = tmux or TmuxBridge(tmux_bin=tmux_bin)

    def resolve_target(self, route: BridgeRouteConfig) -> str:
        return self.tmux.resolve_pane_target(route.tmux_session, route.tmux_window, route.tmux_pane)

    def capture_tail(self, target: str, *, lines: int) -> str:
        return self.tmux.capture_tail(target, lines=lines)

    def send_message(self, route: BridgeRouteConfig, message: str) -> TerminalDispatchResult:
        result = self.tmux.send_message(route.tmux_session, route.tmux_window, route.tmux_pane, message)
        return TerminalDispatchResult(target=result.target, tail=result.tail, running=result.running)

    def send_interrupt(self, route: BridgeRouteConfig) -> TerminalDispatchResult:
        result = self.tmux.send_escape(route.tmux_session, route.tmux_window, route.tmux_pane)
        return TerminalDispatchResult(target=result.target, tail=result.tail, running=result.running)

    def get_current_path(self, route: BridgeRouteConfig) -> str:
        return self.tmux.get_pane_current_path(route.tmux_session, route.tmux_window, route.tmux_pane)
