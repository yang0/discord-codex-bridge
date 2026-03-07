from discord_codex_bridge.tmux_bridge import SessionRef, pane_indicates_running, resolve_target


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
