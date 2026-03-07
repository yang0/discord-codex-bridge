from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import logging
from datetime import datetime, timezone

import discord

from discord_codex_bridge.config import Settings
from discord_codex_bridge.controller import BridgeController
from discord_codex_bridge.models import DiscordRequest
from discord_codex_bridge.shortcuts import ShortcutCommand, build_running_shortcut_help, parse_shortcut_command
from discord_codex_bridge.state import JsonStateStore
from discord_codex_bridge.summary import format_completion, split_discord_message, summarize_progress
from discord_codex_bridge.tmux_bridge import RUNNING_MARKER, RUNNING_PROBE_LINES, TmuxBridge, pane_indicates_running


LOGGER = logging.getLogger(__name__)
DISPATCH_STARTUP_GRACE_SEC = 3


@dataclass(frozen=True)
class RuntimeSnapshot:
    target: str
    latest_output: str
    running: bool


class DiscordCodexBridge(discord.Client):
    def __init__(self, settings: Settings, *, tmux_bridge: TmuxBridge | None = None) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)

        self.settings = settings
        self.tmux = tmux_bridge or TmuxBridge(tmux_bin=settings.tmux_bin)
        self.state_store = JsonStateStore(settings.state_path)
        self.controller = BridgeController(
            progress_interval_sec=settings.progress_interval_sec,
            state=self.state_store.load(),
        )
        self.monitor_task: asyncio.Task[None] | None = None
        self.channel: discord.abc.Messageable | None = None
        self.last_dispatch_error_at: datetime | None = None

    async def on_ready(self) -> None:
        self.channel = self.get_channel(self.settings.discord_channel_id) or await self.fetch_channel(
            self.settings.discord_channel_id
        )
        LOGGER.info("discord bridge ready as %s", self.user)
        if self.monitor_task is None:
            self.monitor_task = asyncio.create_task(self._monitor_loop(), name="codex-monitor-loop")
        await self._kick_idle_queue()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.channel.id != self.settings.discord_channel_id:
            return

        content = _build_message_content(message)
        if not content:
            return

        now = _utcnow()
        try:
            if self.controller.state.active is None and self.controller.state.queue:
                await self._kick_idle_queue(now=now)

            snapshot = await self._capture_runtime_snapshot(lines=self.settings.completion_lines)
            snapshot = await self._reconcile_active_state(snapshot=snapshot, now=now)
            command = parse_shortcut_command(content)

            if snapshot.running:
                await self._handle_running_message(
                    message=message,
                    command=command,
                    snapshot=snapshot,
                    now=now,
                )
                return

            await self._handle_idle_message(message=message, command=command, fallback_content=content, now=now)
        except Exception as exc:
            LOGGER.exception("failed to handle incoming message")
            await self._send_channel_message(f"处理消息失败：{type(exc).__name__}: {exc}")

    async def close(self) -> None:
        if self.monitor_task is not None:
            self.monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.monitor_task
        await super().close()

    async def _monitor_loop(self) -> None:
        while not self.is_closed():
            try:
                await self._monitor_once()
            except Exception:
                LOGGER.exception("monitor tick failed")
            await asyncio.sleep(self.settings.check_interval_sec)

    async def _monitor_once(self) -> None:
        now = _utcnow()
        if self.controller.state.active is None:
            await self._kick_idle_queue(now=now)
            return

        target = await asyncio.to_thread(
            self.tmux.resolve_pane_target,
            self.settings.tmux_session,
            self.settings.tmux_window,
            self.settings.tmux_pane,
        )
        probe = await asyncio.to_thread(self.tmux.capture_tail, target, lines=RUNNING_PROBE_LINES)
        running = pane_indicates_running(probe)

        if running:
            progress_summary = ""
            if self._progress_due(now):
                progress_text = await asyncio.to_thread(
                    self.tmux.capture_tail,
                    target,
                    lines=self.settings.progress_capture_lines,
                )
                progress_summary = summarize_progress(progress_text)
            effects = self.controller.observe(active_running=True, now=now, progress_summary=progress_summary)
        else:
            excerpt = await asyncio.to_thread(
                self.tmux.capture_tail,
                target,
                lines=self.settings.completion_lines,
            )
            active = self.controller.state.active
            assert active is not None
            if not should_treat_task_as_completed(
                started_at=active.started_at,
                now=now,
                probe_text=probe,
                completion_text=excerpt,
                startup_grace_sec=DISPATCH_STARTUP_GRACE_SEC,
            ):
                LOGGER.info("completion suppressed; task still appears active")
                return

            effects = self.controller.observe(
                active_running=False,
                now=now,
                completion_excerpt=format_completion(excerpt, last_lines=self.settings.completion_lines),
            )

        self.state_store.save(self.controller.state)
        await self._execute_effects(effects)

    async def _kick_idle_queue(self, *, now: datetime | None = None) -> None:
        effects = self.controller.observe(active_running=False, now=now or _utcnow())
        if effects:
            self.state_store.save(self.controller.state)
            await self._execute_effects(effects)

    def _progress_due(self, now: datetime) -> bool:
        active = self.controller.state.active
        if active is None:
            return False
        last_progress_at = datetime.fromisoformat(active.last_progress_at)
        return (now - last_progress_at).total_seconds() >= self.settings.progress_interval_sec

    async def _execute_effects(self, effects) -> None:
        suppress_followup_message = False
        for effect in effects:
            if effect.kind == "dispatch" and effect.request is not None:
                try:
                    await asyncio.to_thread(
                        self.tmux.send_message,
                        self.settings.tmux_session,
                        self.settings.tmux_window,
                        self.settings.tmux_pane,
                        effect.request.content,
                    )
                except Exception as exc:
                    LOGGER.exception("dispatch to tmux failed")
                    self.controller.rollback_failed_dispatch(effect.request.request_id)
                    self.state_store.save(self.controller.state)
                    suppress_followup_message = True
                    if self._should_notify_dispatch_error():
                        self.last_dispatch_error_at = _utcnow()
                        await self._send_channel_message(
                            f"转发到 tmux 失败，消息暂存未送达：{type(exc).__name__}: {exc}"
                        )
            elif effect.kind == "discord_message":
                if suppress_followup_message:
                    suppress_followup_message = False
                    continue
                await self._send_channel_message(effect.text)

    def _should_notify_dispatch_error(self) -> bool:
        if self.last_dispatch_error_at is None:
            return True
        elapsed = (_utcnow() - self.last_dispatch_error_at).total_seconds()
        return elapsed >= self.settings.progress_interval_sec

    async def _send_channel_message(self, text: str) -> None:
        if self.channel is None:
            self.channel = self.get_channel(self.settings.discord_channel_id) or await self.fetch_channel(
                self.settings.discord_channel_id
            )
        for chunk in split_discord_message(text):
            await self.channel.send(chunk)

    async def _capture_runtime_snapshot(self, *, lines: int) -> RuntimeSnapshot:
        target = await asyncio.to_thread(
            self.tmux.resolve_pane_target,
            self.settings.tmux_session,
            self.settings.tmux_window,
            self.settings.tmux_pane,
        )
        latest_output = await asyncio.to_thread(self.tmux.capture_tail, target, lines=lines)
        return RuntimeSnapshot(
            target=target,
            latest_output=latest_output,
            running=runtime_output_indicates_running(latest_output),
        )

    async def _reconcile_active_state(self, *, snapshot: RuntimeSnapshot, now: datetime) -> RuntimeSnapshot:
        active = self.controller.state.active
        if active is None or snapshot.running:
            return snapshot

        if not should_treat_task_as_completed(
            started_at=active.started_at,
            now=now,
            probe_text=snapshot.latest_output,
            completion_text=snapshot.latest_output,
            startup_grace_sec=DISPATCH_STARTUP_GRACE_SEC,
        ):
            return snapshot

        effects = self.controller.observe(
            active_running=False,
            now=now,
            completion_excerpt=format_completion(snapshot.latest_output, last_lines=self.settings.completion_lines),
        )
        self.state_store.save(self.controller.state)
        await self._execute_effects(effects)
        return await self._capture_runtime_snapshot(lines=self.settings.completion_lines)

    async def _handle_running_message(
        self,
        *,
        message: discord.Message,
        command: ShortcutCommand | None,
        snapshot: RuntimeSnapshot,
        now: datetime,
    ) -> None:
        if command is None:
            await self._send_channel_message(build_running_shortcut_help(snapshot.latest_output))
            return

        if command.name == "esc":
            await asyncio.to_thread(
                self.tmux.send_escape,
                self.settings.tmux_session,
                self.settings.tmux_window,
                self.settings.tmux_pane,
            )
            await self._send_channel_message("已向运行中的 Codex 发送 ESC。")
            return

        if command.name == "queue":
            if not command.argument:
                await self._send_channel_message("用法：`$q <text>`")
                return
            if self.controller.state.active is None:
                self.controller.claim_active(self._build_placeholder_request(message, now=now), now=now)
            request = self._make_request(message, content=command.argument, suffix="queue")
            position = self.controller.queue_request(request)
            self.state_store.save(self.controller.state)
            await self._send_channel_message(f"已加入队列第 {position} 位，当前任务结束后会自动发送。")
            return

        if command.name == "queue_clear":
            removed = self.controller.clear_queue()
            self.state_store.save(self.controller.state)
            await self._send_channel_message(f"已清空队列，共移除 {removed} 条。")
            return

        if command.name == "insert":
            if not command.argument:
                await self._send_channel_message("用法：`$insert <text>`")
                return
            await asyncio.to_thread(
                self.tmux.send_message,
                self.settings.tmux_session,
                self.settings.tmux_window,
                self.settings.tmux_pane,
                command.argument,
            )
            await self._send_channel_message("已插入到运行中的 Codex。")
            return

        await self._send_channel_message(build_running_shortcut_help(snapshot.latest_output))

    async def _handle_idle_message(
        self,
        *,
        message: discord.Message,
        command: ShortcutCommand | None,
        fallback_content: str,
        now: datetime,
    ) -> None:
        if command is None:
            request = self._make_request(message, content=fallback_content)
            effects = self.controller.start_request(request, now=now)
            self.state_store.save(self.controller.state)
            await self._execute_effects(effects)
            return

        if command.name == "esc":
            await self._send_channel_message("Codex 已结束运行，无需中断。")
            return

        if command.name == "queue_clear":
            removed = self.controller.clear_queue()
            self.state_store.save(self.controller.state)
            await self._send_channel_message(f"Codex 已结束运行；已清空队列 {removed} 条。")
            return

        if command.name in {"queue", "insert"}:
            if not command.argument:
                usage = "$q <text>" if command.name == "queue" else "$insert <text>"
                await self._send_channel_message(f"用法：`{usage}`")
                return
            request = self._make_request(message, content=command.argument, suffix=command.name)
            effects = self.controller.start_request(request, now=now)
            self.state_store.save(self.controller.state)
            await self._execute_effects(effects)
            return

        request = self._make_request(message, content=fallback_content)
        effects = self.controller.start_request(request, now=now)
        self.state_store.save(self.controller.state)
        await self._execute_effects(effects)

    def _make_request(self, message: discord.Message, *, content: str, suffix: str = "direct") -> DiscordRequest:
        return DiscordRequest(
            request_id=f"{message.id}:{suffix}",
            channel_id=message.channel.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            content=content,
            created_at=_utcnow().isoformat(),
        )

    def _build_placeholder_request(self, message: discord.Message, *, now: datetime) -> DiscordRequest:
        return DiscordRequest(
            request_id=f"external-running:{int(now.timestamp())}",
            channel_id=message.channel.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            content="(existing running Codex task)",
            created_at=now.isoformat(),
        )


def _build_message_content(message: discord.Message) -> str:
    parts = [message.content.strip()] if message.content.strip() else []
    parts.extend(attachment.url for attachment in message.attachments)
    return "\n\n".join(parts).strip()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def runtime_output_indicates_running(text: str) -> bool:
    return RUNNING_MARKER in text or pane_indicates_running(text)


def should_treat_task_as_completed(
    *,
    started_at: str,
    now: datetime,
    probe_text: str,
    completion_text: str,
    startup_grace_sec: int,
) -> bool:
    if pane_indicates_running(probe_text):
        return False

    started = datetime.fromisoformat(started_at)
    if (now - started).total_seconds() < startup_grace_sec:
        return False

    if RUNNING_MARKER in completion_text:
        return False

    return True
