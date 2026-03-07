from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from discord_codex_bridge.models import ActiveTask, BridgeEffect, BridgeState, DiscordRequest


class BridgeController:
    def __init__(self, *, progress_interval_sec: int, state: BridgeState | None = None) -> None:
        self.progress_interval_sec = progress_interval_sec
        self.state = state or BridgeState()

    def submit(self, request: DiscordRequest, *, now: datetime) -> list[BridgeEffect]:
        if self.state.active is None:
            self.state.active = ActiveTask.from_request(request, now=now)
            return [
                BridgeEffect(kind="dispatch", request=request),
                BridgeEffect(kind="discord_message", text="消息已转发到 tmux，开始处理。"),
            ]

        self.state.queue.append(request)
        position = len(self.state.queue)
        return [BridgeEffect(kind="discord_message", text=f"Codex 仍在运行，已排队第 {position} 位。")]

    def observe(
        self,
        *,
        active_running: bool,
        now: datetime,
        progress_summary: str = "",
        completion_excerpt: str = "",
    ) -> list[BridgeEffect]:
        effects: list[BridgeEffect] = []

        if self.state.active is None:
            return self._start_next_if_idle(now=now)

        if active_running:
            last_progress_at = datetime.fromisoformat(self.state.active.last_progress_at)
            elapsed = (now - last_progress_at).total_seconds()
            if elapsed >= self.progress_interval_sec:
                summary = progress_summary or "5 分钟进度：Codex 仍在运行。"
                effects.append(BridgeEffect(kind="discord_message", text=summary))
                self.state.active.touch_progress(now=now)
            return effects

        completion_text = completion_excerpt or "Codex 当前任务已结束。"
        effects.append(BridgeEffect(kind="discord_message", text=completion_text))
        self.state.active = None
        effects.extend(self._start_next_if_idle(now=now, announce=True))
        return effects

    def _start_next_if_idle(self, *, now: datetime, announce: bool = False) -> list[BridgeEffect]:
        if self.state.active is not None or not self.state.queue:
            return []

        next_request = self.state.queue.pop(0)
        self.state.active = ActiveTask.from_request(next_request, now=now)
        effects = [BridgeEffect(kind="dispatch", request=next_request)]
        if announce:
            effects.append(BridgeEffect(kind="discord_message", text="上一条已结束，开始处理下一条排队消息。"))
        return effects

    def rollback_failed_dispatch(self, request_id: str) -> None:
        active = self.state.active
        if active is None or active.request_id != request_id:
            return

        request = DiscordRequest(
            request_id=active.request_id,
            channel_id=active.channel_id,
            author_id=active.author_id,
            author_name=active.author_name,
            content=active.content,
            created_at=active.created_at,
        )
        self.state.active = None
        if not self.state.queue or self.state.queue[0].request_id != request_id:
            self.state.queue.insert(0, request)
