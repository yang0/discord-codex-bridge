from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShortcutCommand:
    name: str
    argument: str = ""


def parse_shortcut_command(text: str) -> ShortcutCommand | None:
    stripped = text.strip()
    if stripped == "$esc":
        return ShortcutCommand(name="esc", argument="")
    if stripped == "$qx":
        return ShortcutCommand(name="queue_clear", argument="")
    if stripped == "$q":
        return ShortcutCommand(name="queue", argument="")
    if stripped.startswith("$q "):
        return ShortcutCommand(name="queue", argument=stripped[3:].strip())
    if stripped == "$insert":
        return ShortcutCommand(name="insert", argument="")
    if stripped.startswith("$insert "):
        return ShortcutCommand(name="insert", argument=stripped[8:].strip())
    return None


def build_running_shortcut_help(latest_output: str) -> str:
    clean_output = latest_output.strip() or "(latest tmux output is empty)"
    return (
        "Codex 仍在运行。当前不会自动接收普通消息。\n"
        "可用快捷方式：\n"
        "- `$esc`：中断当前正在运行的 Codex\n"
        "- `$q <text>`：放入队列，等当前任务结束后自动发送\n"
        "- `$qx`：清空当前队列\n"
        "- `$insert <text>`：立刻插入到当前运行中的 Codex\n\n"
        "下面附 tmux 最新 100 行：\n\n"
        f"{clean_output}"
    )
