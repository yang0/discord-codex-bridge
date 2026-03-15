import json
from pathlib import Path

import pytest

from discord_codex_bridge.models import BridgeRouteConfig, WezTermTargetConfig
from discord_codex_bridge.wezterm_backend import WezTermBackend


class FakeRunner:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if not self.responses:
            raise AssertionError(f'unexpected command: {args}')
        return self.responses.pop(0)


def make_route(tmp_path: Path, **target_kwargs) -> BridgeRouteConfig:
    return BridgeRouteConfig(
        name='windows-dev',
        channel_id=123,
        state_path=tmp_path / 'state.json',
        check_interval_sec=5,
        progress_interval_sec=300,
        progress_capture_lines=220,
        completion_lines=100,
        terminal_target=WezTermTargetConfig(workspace='codex', **target_kwargs),
    )


def make_list_output(*panes: dict) -> str:
    return json.dumps(list(panes))


def test_resolve_target_uses_workspace_and_exact_title(tmp_path: Path):
    runner = FakeRunner(
        [
            make_list_output(
                {
                    'pane_id': 41,
                    'workspace': 'codex',
                    'title': 'codex: other',
                    'cwd': 'file:///Users/test/other',
                },
                {
                    'pane_id': 42,
                    'workspace': 'codex',
                    'title': 'codex: windows-dev',
                    'cwd': 'file:///Users/test/project',
                },
            )
        ]
    )
    backend = WezTermBackend(wezterm_bin='wezterm', runner=runner)

    target = backend.resolve_target(make_route(tmp_path, pane_title='codex: windows-dev'))

    assert target == '42'
    assert runner.calls == [['wezterm', 'cli', 'list', '--format', 'json']]


def test_resolve_target_supports_title_regex(tmp_path: Path):
    runner = FakeRunner(
        [
            make_list_output(
                {
                    'pane_id': 55,
                    'workspace': 'codex',
                    'title': 'codex: windows-dev',
                    'cwd': 'file:///Users/test/project',
                }
            )
        ]
    )
    backend = WezTermBackend(wezterm_bin='wezterm', runner=runner)

    target = backend.resolve_target(make_route(tmp_path, pane_title_regex='^codex: windows-.*$'))

    assert target == '55'


def test_resolve_target_rejects_zero_matches(tmp_path: Path):
    runner = FakeRunner([make_list_output({'pane_id': 1, 'workspace': 'other', 'title': 'x', 'cwd': 'file:///tmp/x'})])
    backend = WezTermBackend(wezterm_bin='wezterm', runner=runner)

    with pytest.raises(ValueError, match='Unable to resolve WezTerm pane'):
        backend.resolve_target(make_route(tmp_path, pane_title='codex: windows-dev'))


def test_resolve_target_rejects_multiple_matches(tmp_path: Path):
    runner = FakeRunner(
        [
            make_list_output(
                {
                    'pane_id': 41,
                    'workspace': 'codex',
                    'title': 'codex: windows-dev',
                    'cwd': 'file:///Users/test/project-a',
                },
                {
                    'pane_id': 42,
                    'workspace': 'codex',
                    'title': 'codex: windows-dev',
                    'cwd': 'file:///Users/test/project-b',
                },
            )
        ]
    )
    backend = WezTermBackend(wezterm_bin='wezterm', runner=runner)

    with pytest.raises(ValueError, match='matched multiple WezTerm panes'):
        backend.resolve_target(make_route(tmp_path, pane_title='codex: windows-dev'))


def test_get_current_path_reads_cwd_from_list_output(tmp_path: Path):
    runner = FakeRunner(
        [
            make_list_output(
                {
                    'pane_id': 42,
                    'workspace': 'codex',
                    'title': 'codex: windows-dev',
                    'cwd': 'file:///C:/Users/test/project',
                }
            )
        ]
    )
    backend = WezTermBackend(wezterm_bin='wezterm', runner=runner)

    current_path = backend.get_current_path(make_route(tmp_path, pane_title='codex: windows-dev'))

    assert current_path == 'C:/Users/test/project'


def test_capture_tail_uses_get_text_command(tmp_path: Path):
    runner = FakeRunner(['tail output'])
    backend = WezTermBackend(wezterm_bin='wezterm', runner=runner)

    tail = backend.capture_tail('42', lines=100)

    assert tail == 'tail output'
    assert runner.calls == [['wezterm', 'cli', 'get-text', '--pane-id', '42', '--start-line', '-100']]


def test_send_message_uses_send_text_and_returns_latest_tail(tmp_path: Path):
    runner = FakeRunner(
        [
            make_list_output(
                {
                    'pane_id': 42,
                    'workspace': 'codex',
                    'title': 'codex: windows-dev',
                    'cwd': 'file:///C:/Users/test/project',
                }
            ),
            '',
            'working... esc to interrupt',
        ]
    )
    backend = WezTermBackend(wezterm_bin='wezterm', runner=runner)

    result = backend.send_message(make_route(tmp_path, pane_title='codex: windows-dev'), 'refine it')

    assert result.target == '42'
    assert result.running is True
    assert runner.calls == [
        ['wezterm', 'cli', 'list', '--format', 'json'],
        ['wezterm', 'cli', 'send-text', '--pane-id', '42', '--no-paste', 'refine it\n'],
        ['wezterm', 'cli', 'get-text', '--pane-id', '42', '--start-line', '-20'],
    ]


def test_send_interrupt_sends_escape_character_without_paste(tmp_path: Path):
    runner = FakeRunner(
        [
            make_list_output(
                {
                    'pane_id': 42,
                    'workspace': 'codex',
                    'title': 'codex: windows-dev',
                    'cwd': 'file:///C:/Users/test/project',
                }
            ),
            '',
            'idle',
        ]
    )
    backend = WezTermBackend(wezterm_bin='wezterm', runner=runner)

    result = backend.send_interrupt(make_route(tmp_path, pane_title='codex: windows-dev'))

    assert result.target == '42'
    assert result.running is False
    assert runner.calls == [
        ['wezterm', 'cli', 'list', '--format', 'json'],
        ['wezterm', 'cli', 'send-text', '--pane-id', '42', '--no-paste', '\x1b'],
        ['wezterm', 'cli', 'get-text', '--pane-id', '42', '--start-line', '-20'],
    ]
