from discord_codex_bridge.tmux_bridge import SessionRef, TmuxBridge, pane_indicates_running, resolve_target


def test_resolve_tmux_target_uses_exact_session_name_first():
    sessions = [
        SessionRef(name="bridge", group="", attached=True, last_attached=10),
        SessionRef(name="bridge-2", group="bridge", attached=True, last_attached=20),
    ]

    assert resolve_target("bridge", 0, 0, sessions) == "bridge:0.0"


def test_resolve_tmux_target_uses_session_group_when_exact_session_missing():
    sessions = [
        SessionRef(name="codex", group="", attached=False, last_attached=5),
        SessionRef(name="bridge-2", group="bridge", attached=True, last_attached=20),
    ]

    assert resolve_target("bridge", 0, 0, sessions) == "bridge-2:0.0"


def test_resolve_tmux_target_uses_prefix_match_as_last_fallback():
    sessions = [
        SessionRef(name="bridge-3", group="", attached=True, last_attached=30),
        SessionRef(name="bridge-2", group="", attached=False, last_attached=20),
    ]

    assert resolve_target("bridge", 0, 0, sessions) == "bridge-3:0.0"


def test_pane_indicates_running_uses_esc_to_interrupt_marker():
    assert pane_indicates_running("working... esc to interrupt") is True
    assert pane_indicates_running("working... press any key") is False


def test_list_sessions_parses_psmux_plain_output(monkeypatch):
    bridge = TmuxBridge(tmux_bin="tmux")

    def fake_run(*args: str) -> str:
        assert args == (
            "list-sessions",
            "-F",
            "#{session_name}\t#{session_group}\t#{session_attached}\t#{session_last_attached}",
        )
        return "\n".join(
            [
                "default: 1 windows (created Sun Mar 15 10:09:09 2026) (attached)",
                "windows-dev: 1 windows (created Sun Mar 15 10:10:24 2026)",
            ]
        )

    monkeypatch.setattr(bridge, "_run", fake_run)

    sessions = bridge.list_sessions()

    assert sessions == [
        SessionRef(name="default", group="", attached=True, last_attached=0),
        SessionRef(name="windows-dev", group="", attached=False, last_attached=0),
    ]


def test_capture_tail_uses_separate_p_and_t_flags(monkeypatch):
    bridge = TmuxBridge(tmux_bin="tmux")
    captured: list[tuple[str, ...]] = []

    def fake_run(*args: str) -> str:
        captured.append(args)
        return "tail output"

    monkeypatch.setattr(bridge, "_run", fake_run)

    tail = bridge.capture_tail("windows-dev:0.0", lines=20)

    assert tail == "tail output"
    assert captured == [("capture-pane", "-p", "-t", "windows-dev:0.0", "-S", "-20")]
