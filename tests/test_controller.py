from datetime import datetime, timedelta, timezone

from discord_codex_bridge.controller import BridgeController
from discord_codex_bridge.models import DiscordRequest


def make_request(request_id: str, content: str) -> DiscordRequest:
    return DiscordRequest(
        request_id=request_id,
        channel_id=1479951053494554736,
        author_id=1,
        author_name="tester",
        content=content,
        created_at="2026-03-08T05:30:00+00:00",
    )


def test_submit_queues_when_active_task_exists():
    t0 = datetime(2026, 3, 8, 5, 30, tzinfo=timezone.utc)
    controller = BridgeController(progress_interval_sec=300)

    first = controller.submit(make_request("r1", "first"), now=t0)
    second = controller.submit(make_request("r2", "second"), now=t0 + timedelta(seconds=5))

    assert [effect.kind for effect in first] == ["dispatch", "discord_message"]
    assert controller.state.active is not None
    assert len(controller.state.queue) == 1
    assert second[0].kind == "discord_message"
    assert "已排队第 1 位" in second[0].text


def test_observe_sends_progress_only_after_interval():
    t0 = datetime(2026, 3, 8, 5, 30, tzinfo=timezone.utc)
    controller = BridgeController(progress_interval_sec=300)
    controller.submit(make_request("r1", "first"), now=t0)

    before = controller.observe(active_running=True, now=t0 + timedelta(minutes=4))
    after = controller.observe(active_running=True, now=t0 + timedelta(minutes=5), progress_summary="still running")

    assert before == []
    assert [effect.kind for effect in after] == ["discord_message"]
    assert "still running" in after[0].text


def test_observe_completion_dispatches_next_queued_request():
    t0 = datetime(2026, 3, 8, 5, 30, tzinfo=timezone.utc)
    controller = BridgeController(progress_interval_sec=300)
    controller.submit(make_request("r1", "first"), now=t0)
    controller.submit(make_request("r2", "second"), now=t0 + timedelta(seconds=3))

    effects = controller.observe(
        active_running=False,
        now=t0 + timedelta(minutes=6),
        completion_excerpt="last 100 lines",
    )

    assert [effect.kind for effect in effects] == ["discord_message", "dispatch", "discord_message"]
    assert controller.state.active is not None
    assert controller.state.active.request_id == "r2"
    assert len(controller.state.queue) == 0
    assert "last 100 lines" in effects[0].text
    assert "开始处理下一条排队消息" in effects[2].text


def test_rollback_failed_dispatch_requeues_active_request():
    t0 = datetime(2026, 3, 8, 5, 30, tzinfo=timezone.utc)
    controller = BridgeController(progress_interval_sec=300)
    controller.submit(make_request("r1", "first"), now=t0)

    controller.rollback_failed_dispatch("r1")

    assert controller.state.active is None
    assert [item.request_id for item in controller.state.queue] == ["r1"]
