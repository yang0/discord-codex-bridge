from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone

import discord

from discord_codex_bridge.config import Settings
from discord_codex_bridge.controller import BridgeController
from discord_codex_bridge.models import DiscordRequest
from discord_codex_bridge.state import JsonStateStore
from discord_codex_bridge.summary import format_completion, split_discord_message, summarize_progress
from discord_codex_bridge.tmux_bridge import RUNNING_PROBE_LINES, TmuxBridge, pane_indicates_running


LOGGER = logging.getLogger(__name__)


class DiscordCodexBridge(discord.Client):
    def __init__(self, settings: Settings, *, tmux_bridge: TmuxBridge | None = None) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(intents=intents)

        self.settings = settings
        self.tmux = tmux_bridge or TmuxBridge()
        self.state_store = JsonStateStore(settings.state_path)
        self.controller = BridgeController(
            progress_interval_sec=settings.progress_interval_sec,
            state=self.state_store.load(),
        )
        self.monitor_task: asyncio.Task[None] | None = None
        self.channel: discord.abc.Messageable | None = None

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

        request = DiscordRequest(
            request_id=str(message.id),
            channel_id=message.channel.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            content=content,
            created_at=_utcnow().isoformat(),
        )
        effects = self.controller.submit(request, now=_utcnow())
        self.state_store.save(self.controller.state)
        await self._execute_effects(effects)

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
        for effect in effects:
            if effect.kind == "dispatch" and effect.request is not None:
                await asyncio.to_thread(
                    self.tmux.send_message,
                    self.settings.tmux_session,
                    self.settings.tmux_window,
                    self.settings.tmux_pane,
                    effect.request.content,
                )
            elif effect.kind == "discord_message":
                await self._send_channel_message(effect.text)

    async def _send_channel_message(self, text: str) -> None:
        if self.channel is None:
            self.channel = self.get_channel(self.settings.discord_channel_id) or await self.fetch_channel(
                self.settings.discord_channel_id
            )
        for chunk in split_discord_message(text):
            await self.channel.send(chunk)


def _build_message_content(message: discord.Message) -> str:
    parts = [message.content.strip()] if message.content.strip() else []
    parts.extend(attachment.url for attachment in message.attachments)
    return "\n\n".join(parts).strip()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
