from __future__ import annotations


def split_discord_message(text: str, *, limit: int = 1900) -> list[str]:
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    current = text
    while current:
        if len(current) <= limit:
            parts.append(current)
            break
        boundary = current.rfind("\n", 0, limit)
        if boundary <= 0:
            boundary = limit
        parts.append(current[:boundary])
        current = current[boundary:]
        if current.startswith("\n"):
            current = current[1:]
    return parts


def summarize_progress(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "5 分钟进度：Codex 仍在运行，但最近没有可见输出。"

    recent: list[str] = []
    for line in reversed(lines[-40:]):
        if line not in recent:
            recent.append(line)
        if len(recent) == 4:
            break
    recent.reverse()
    body = "\n".join(f"- {line[:240]}" for line in recent)
    return f"5 分钟进度：Codex 仍在运行。\n{body}"


def format_completion(excerpt: str, *, last_lines: int) -> str:
    clean_excerpt = excerpt.strip() or "(最后输出为空)"
    return f"Codex 当前任务已结束。下面附最后 {last_lines} 行输出，供你复盘：\n\n{clean_excerpt}"
