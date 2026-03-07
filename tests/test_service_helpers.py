from datetime import datetime, timedelta, timezone

from discord_codex_bridge.service import should_treat_task_as_completed


def test_completion_is_suppressed_during_startup_grace_window():
    started_at = datetime(2026, 3, 8, 6, 10, tzinfo=timezone.utc)
    now = started_at + timedelta(seconds=1)

    assert should_treat_task_as_completed(
        started_at=started_at.isoformat(),
        now=now,
        probe_text='no marker here',
        completion_text='no marker here either',
        startup_grace_sec=3,
    ) is False


def test_completion_is_suppressed_if_completion_excerpt_still_has_marker():
    started_at = datetime(2026, 3, 8, 6, 10, tzinfo=timezone.utc)
    now = started_at + timedelta(seconds=6)

    assert should_treat_task_as_completed(
        started_at=started_at.isoformat(),
        now=now,
        probe_text='no marker here',
        completion_text='partial output\n◦ Working (2s • esc to interrupt)',
        startup_grace_sec=3,
    ) is False


def test_completion_is_allowed_after_grace_when_no_marker_remains():
    started_at = datetime(2026, 3, 8, 6, 10, tzinfo=timezone.utc)
    now = started_at + timedelta(seconds=6)

    assert should_treat_task_as_completed(
        started_at=started_at.isoformat(),
        now=now,
        probe_text='no marker here',
        completion_text='final answer\nPONG',
        startup_grace_sec=3,
    ) is True
