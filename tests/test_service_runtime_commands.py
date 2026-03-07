import asyncio
from pathlib import Path
from types import SimpleNamespace

from discord_codex_bridge.config import Settings
from discord_codex_bridge.service import DiscordCodexBridge, RuntimeSnapshot
from discord_codex_bridge.shortcuts import ShortcutCommand


class FakeTmux:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.escape_count = 0

    def send_message(self, requested_session: str, window: int, pane: int, message: str):
        self.sent_messages.append(message)
        return None

    def send_escape(self, requested_session: str, window: int, pane: int):
        self.escape_count += 1
        return None


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        discord_bot_token='token',
        discord_channel_id=123,
        tmux_bin='/tmp/tmux',
        tmux_session='oc_backup',
        tmux_window=0,
        tmux_pane=0,
        check_interval_sec=5,
        progress_interval_sec=300,
        progress_capture_lines=220,
        completion_lines=100,
        state_path=tmp_path / 'state.json',
    )


def make_message(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=111,
        content=content,
        attachments=[],
        channel=SimpleNamespace(id=123),
        author=SimpleNamespace(bot=False, id=9, display_name='tester'),
    )


def test_running_plain_message_returns_shortcut_help_and_latest_output(tmp_path: Path):
    bridge = DiscordCodexBridge(make_settings(tmp_path), tmux_bridge=FakeTmux())
    messages: list[str] = []

    async def fake_send(text: str) -> None:
        messages.append(text)

    bridge._send_channel_message = fake_send  # type: ignore[method-assign]
    snapshot = RuntimeSnapshot(target='pane', latest_output='line1\nline2', running=True)

    asyncio.run(
        bridge._handle_running_message(
            message=make_message('hello'),
            command=None,
            snapshot=snapshot,
            now=bridge.controller.state.active.started_at if bridge.controller.state.active else __import__('datetime').datetime.now(__import__('datetime').timezone.utc),
        )
    )

    assert len(messages) == 1
    assert '$esc' in messages[0]
    assert 'line1' in messages[0]
    assert bridge.controller.state.queue == []


def test_running_queue_command_enqueues_without_dispatch(tmp_path: Path):
    bridge = DiscordCodexBridge(make_settings(tmp_path), tmux_bridge=FakeTmux())
    messages: list[str] = []
    executed = []

    async def fake_send(text: str) -> None:
        messages.append(text)

    async def fake_execute(effects) -> None:
        executed.extend(effects)

    bridge._send_channel_message = fake_send  # type: ignore[method-assign]
    bridge._execute_effects = fake_execute  # type: ignore[method-assign]
    snapshot = RuntimeSnapshot(target='pane', latest_output='running\nesc to interrupt', running=True)
    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)

    asyncio.run(
        bridge._handle_running_message(
            message=make_message('$q follow up'),
            command=ShortcutCommand(name='queue', argument='follow up'),
            snapshot=snapshot,
            now=now,
        )
    )

    assert executed == []
    assert bridge.controller.state.active is not None
    assert [item.content for item in bridge.controller.state.queue] == ['follow up']
    assert '已加入队列第 1 位' in messages[0]


def test_running_insert_command_sends_message_immediately(tmp_path: Path):
    tmux = FakeTmux()
    bridge = DiscordCodexBridge(make_settings(tmp_path), tmux_bridge=tmux)
    messages: list[str] = []

    async def fake_send(text: str) -> None:
        messages.append(text)

    bridge._send_channel_message = fake_send  # type: ignore[method-assign]
    snapshot = RuntimeSnapshot(target='pane', latest_output='running\nesc to interrupt', running=True)
    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)

    asyncio.run(
        bridge._handle_running_message(
            message=make_message('$insert refine it'),
            command=ShortcutCommand(name='insert', argument='refine it'),
            snapshot=snapshot,
            now=now,
        )
    )

    assert tmux.sent_messages == ['refine it']
    assert '已插入到运行中的 Codex' in messages[0]


def test_idle_queue_command_starts_immediately(tmp_path: Path):
    bridge = DiscordCodexBridge(make_settings(tmp_path), tmux_bridge=FakeTmux())
    executed = []

    async def fake_execute(effects) -> None:
        executed.extend(effects)

    async def fake_send(text: str) -> None:
        raise AssertionError(text)

    bridge._execute_effects = fake_execute  # type: ignore[method-assign]
    bridge._send_channel_message = fake_send  # type: ignore[method-assign]
    now = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)

    asyncio.run(
        bridge._handle_idle_message(
            message=make_message('$q follow up'),
            command=ShortcutCommand(name='queue', argument='follow up'),
            fallback_content='$q follow up',
            now=now,
        )
    )

    assert bridge.controller.state.active is not None
    assert bridge.controller.state.active.content == 'follow up'
    assert bridge.controller.state.queue == []
    assert [effect.kind for effect in executed] == ['dispatch', 'discord_message']
