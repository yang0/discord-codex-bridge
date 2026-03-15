# Windows Psmux Design

## Goal

在 Windows 上不再把 `WezTerm` 作为默认终端 backend，而是优先使用 `psmux`，尽量复用现有 `tmux` 路径和配置模型。

## Decision

- 保留 `wezterm` 显式 backend，避免打断现有手动配置。
- 把 Windows 下 `TERMINAL_BACKEND=auto` 的默认解析改为 `tmux`。
- 通过兼容 `psmux` 的 CLI 差异来复用 `TmuxBridge`，而不是新增一套 `PsmuxBackend`。

## Why

实机验证表明：

- `psmux` 安装后提供 `psmux` / `pmux` / `tmux` 别名，适合直接接入现有 `tmux` backend。
- `send-keys`、`display-message`、`capture-pane` 在真实附着会话里可用。
- 但 `psmux` 对 `list-sessions -F ...` 不返回 tmux 风格格式化输出。
- 但 `psmux` 对合并短参数 `capture-pane -pt ...` 不兼容，拆成 `-p -t` 后正常。

因此最小、稳定的实现不是新增 backend，而是让 `TmuxBridge` 兼容两种 CLI 行为。

## Scope

- 更新 `TmuxBridge` 的 session 解析与 `capture-pane` 调用。
- 更新 Windows 下自动 backend 选择逻辑与相关测试。
- 更新 README / 示例配置，使 Windows 推荐路径改为 `psmux` + `tmux_session`。
- 保留显式 `wezterm` backend 作为兼容选项。

## Verification

- 单元测试覆盖 `psmux` 风格 session 列表解析与 `capture-pane` 参数形状。
- 现有测试套件全量通过。
- Windows 真机 smoke test：真实 `psmux` 会话可被 bridge 解析、注入文本并抓取尾部输出。
