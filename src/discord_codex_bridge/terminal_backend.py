from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from discord_codex_bridge.models import BridgeRouteConfig


@dataclass(frozen=True)
class TerminalDispatchResult:
    target: str
    tail: str
    running: bool


class TerminalBackend(Protocol):
    def resolve_target(self, route: BridgeRouteConfig) -> str:
        ...

    def capture_tail(self, target: str, *, lines: int) -> str:
        ...

    def send_message(self, route: BridgeRouteConfig, message: str) -> TerminalDispatchResult:
        ...

    def send_interrupt(self, route: BridgeRouteConfig) -> TerminalDispatchResult:
        ...

    def get_current_path(self, route: BridgeRouteConfig) -> str:
        ...
