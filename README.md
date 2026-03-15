# Discord Codex Bridge

一个独立 sidecar 服务：**单个进程**同时桥接多个 Discord 频道到多个终端里的 Codex 会话。它运行在 OpenClaw 外部，所以即使 OpenClaw 主进程不在线，桥接仍然可用。

## What It Does

- 一个 bot token + 一个进程，管理多条 Discord ↔ 终端会话路由
- 每条路由独立维护自己的活跃任务、队列、进度节奏和状态文件
- 路由之间互不阻塞：某个会话在忙，不会卡住其它会话
- 支持配置文件热重载；配置错误时保留 last-known-good 运行态
- 任务完成时发送尾部输出；运行中支持中断、排队和插入消息
- Linux 默认使用 `tmux`，Windows 默认使用 `WezTerm`

## Runtime Shortcuts

当某条路由对应的 Codex 正在运行时，bot 支持这些快捷指令：

- `h`：查看快捷方式说明文档
- `ai <text>`：直接调用 AI 处理本地上下文，不把消息发给终端会话
- `f [lines]`：直接抓取当前终端会话的尾部输出，默认最后 100 行
- `p`：查看当前路由的自动抓取设置
- `p <interval_sec> <lines>`：设置当前路由自动抓取的时间间隔和抓取行数
- `e`：发送 `Esc` 中断当前运行
- `q <text>`：把消息加入该路由自己的队列
- `qx`：清空该路由自己的排队消息
- `i <text>`：立即把消息插入当前正在运行的 Codex 会话

如果某条路由仍在运行，而用户发送的是普通消息，bot 会返回快捷指令提示和最新终端输出片段，而不是静默排队。

### `ai` Shortcut

`ai` 用于让 bridge **直接**调用 AI 处理请求，而不是把文本注入终端会话。当前实现会：

- 复用本机 `~/.codex/config.toml` 里的模型配置
- 复用本机 `~/.codex/auth.json` 里的认证信息
- **不会**调用 `codex exec`
- 自动把当前路由名、终端目标标识、最新输出、当前忙碌状态、当前工作目录作为上下文喂给 AI
- 允许 AI 在当前终端工作目录内查找并读取文本文件，然后把结果直接回复到 Discord

例如用户发送：

```text
ai 把这个文件发我
```

bridge 会让 AI 结合当前上下文决定该找哪个文件、读取哪些文本内容，并把结果直接发回 Discord。

### `p` Shortcut

`p` 用于查看或调整当前路由的自动抓取设置，也就是运行中周期性进度消息的两个参数：

- 自动抓取间隔：`progress_interval_sec`
- 自动抓取行数：`progress_capture_lines`

示例：

```text
p
p 60 200
```

行为说明：

- `p`：返回当前路由的有效自动抓取设置
- `p 60 200`：把当前路由设置为“每 60 秒抓取 200 行”
- 设置会立即生效
- 设置会写入当前路由本地状态文件，服务重启后仍会保留

## Requirements

- Python 3.10+
- Linux: `tmux`
- Windows: `WezTerm`
- 已加入服务器的 Discord bot
- 为 bot 开启 Discord `MESSAGE CONTENT INTENT`
- 每条路由目标终端中已经有一个可交互的 Codex TUI
- 如果要使用 `ai`，本机还需要已有可用的 Codex CLI 配置文件：`~/.codex/config.toml` 和 `~/.codex/auth.json`

## Backend Model

第一期跨平台支持采用**单进程单 backend**：

- `TERMINAL_BACKEND=auto`：Linux 选 `tmux`，Windows 选 `wezterm`
- `TERMINAL_BACKEND=tmux`：显式使用 `tmux`
- `TERMINAL_BACKEND=wezterm`：显式使用 `WezTerm`

当前**不支持**同一个 bridge 进程里部分路由走 `tmux`、部分路由走 `WezTerm`。

## Configuration

### 1. Global Settings In `.env`

复制 `.env.example` 为本地 `.env`，这里只放**全局设置**：

```env
DISCORD_BOT_TOKEN=your_bot_token
BRIDGES_CONFIG_PATH=./bridges.local.json
TERMINAL_BACKEND=auto
TMUX_BIN=/absolute/path/to/tmux
WEZTERM_BIN=wezterm
TMUX_WINDOW=0
TMUX_PANE=0
CHECK_INTERVAL_SEC=5
PROGRESS_INTERVAL_SEC=300
PROGRESS_CAPTURE_LINES=220
COMPLETION_LINES=100
```

说明：

- `DISCORD_BOT_TOKEN` 只放在本地 `.env`，不要提交到仓库
- `BRIDGES_CONFIG_PATH` 指向本地多路由 JSON 配置
- `TERMINAL_BACKEND` 默认为 `auto`
- `TMUX_BIN` 建议在 Linux 上写绝对路径，方便在 `systemd --user` 下运行
- `WEZTERM_BIN` 默认为 `wezterm`
- `TMUX_WINDOW`、`TMUX_PANE`、轮询/进度参数是全局默认值；只有 `tmux` backend 会用到前两个字段

### 2. Route Settings In `bridges.local.json`

复制 `bridges.example.json` 为本地 `bridges.local.json`，这里只放**各路由配置**。

### Linux / tmux Route Example

```json
{
  "bridges": [
    {
      "name": "backup",
      "enabled": true,
      "channel_id": 123456789012345678,
      "tmux_session": "session_alpha",
      "state_path": "./state/bridge_state_backup.json"
    }
  ]
}
```

### Windows / WezTerm Route Example

```json
{
  "bridges": [
    {
      "name": "windows-dev",
      "enabled": true,
      "channel_id": 234567890123456789,
      "terminal_target": {
        "workspace": "codex",
        "pane_title_regex": "^Codex: windows-dev$",
        "cwd_contains": "projectHome"
      },
      "state_path": "./state/bridge_state_windows_dev.json"
    }
  ]
}
```

`bridges.example.json` 同时展示了两种目标形状。运行时请只保留与你当前 `TERMINAL_BACKEND` 对应的那类路由。

字段说明：

- 每条路由至少都需要：
  - `name`
  - `channel_id`
  - `state_path`
- `tmux` route 需要：
  - `tmux_session`
  - 可选 `tmux_window`、`tmux_pane`
- `wezterm` route 需要：
  - `terminal_target.workspace`
  - 可选 `terminal_target.pane_title`
  - 可选 `terminal_target.pane_title_regex`
  - 可选 `terminal_target.cwd_contains`

WezTerm selector 解析顺序：

- 先按 `workspace` 过滤
- 再按 `pane_title` 精确匹配
- 再按 `pane_title_regex` 正则匹配
- 再按 `cwd_contains` 做路径子串过滤
- 命中 0 个或多个 pane 都会视为配置/解析失败

通用说明：

- `name`：稳定路由名，用于识别和热重载 diff
- `enabled: false` 的路由会被忽略，不会启动
- `state_path` 建议每条路由单独一个文件，避免状态互相污染
- `bridges.example.json` 只放占位值，真实频道/会话名只写入本地 `bridges.local.json`

## Privacy And Git Hygiene

以下内容默认应只存在本地，不进入仓库：

- `.env`
- `.env.*`
- `bridges.local.json`
- `state/*.json`

仓库内只保留模板文件：

- `.env.example`
- `bridges.example.json`

这意味着可以安全提交配置结构、字段说明和占位示例，但**不要**提交真实 token、真实频道 ID、真实 tmux session 名、真实 WezTerm selector 或真实状态文件路径。

## Hot Reload

服务会监视 `bridges.local.json` 的文件修改时间，并在后续 monitor tick 中自动重载：

- 新增路由：自动创建新的运行时
- 修改路由节奏参数：更新对应路由运行时
- 删除或禁用路由：如果该路由仍有活跃任务，会先进入 draining，等任务和队列清空后再彻底移除
- 配置文件格式错误：记录日志并继续保留当前 last-known-good 路由集，不会把正在运行的桥接打挂

## Local Run

```bash
cd /path/to/discord-codex-bridge
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
cp bridges.example.json bridges.local.json
python -m discord_codex_bridge --env-file .env
```

Windows PowerShell 示例：

```powershell
cd E:\projectHome\discord-codex-bridge
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
Copy-Item bridges.example.json bridges.local.json
python -m discord_codex_bridge --env-file .env
```

## Migration From Old Per-Route Services

如果你以前是“一条路由一个服务 / 一个 `.env.xxx` / 一个 systemd unit` / 一个 Windows 启动任务”：

1. 把 bot token 和全局默认参数收敛到一个 `.env`
2. 把各路由的 `channel_id`、`tmux_session`、`state_path` 合并进一个 `bridges.local.json`
3. 给每条路由分配独立 `state_path`
4. 停掉旧的多实例服务，只保留一个多桥接服务

这个改造的目标是**直接替换旧方案**：部署面从“多个 bridge 进程”收敛为“一个 bridge 进程 + 一个本地多路由配置文件”。

## Tests

```bash
cd /path/to/discord-codex-bridge
pytest -q
```

## Linux systemd

推荐使用新的单进程 unit：`systemd/discord-codex-multi-bridge.service`。

```bash
mkdir -p ~/.config/systemd/user
cp systemd/discord-codex-multi-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now discord-codex-multi-bridge.service
systemctl --user status discord-codex-multi-bridge.service
```

如果本机仍启用了旧的按路由拆分服务，迁移时先停掉旧服务，再启用新的单进程服务。

仓库中保留 `systemd/discord-codex-bridge.service` 作为旧命名示例；新部署默认使用 `discord-codex-multi-bridge.service`。

## Windows Startup

Windows 没有 `systemd --user`。推荐把 bridge 放到一个登录后启动的任务里，例如 Task Scheduler：

```powershell
schtasks /create /tn "discord-codex-bridge" /sc onlogon /tr "powershell -NoProfile -ExecutionPolicy Bypass -Command `"cd E:\projectHome\discord-codex-bridge; .\.venv\Scripts\Activate.ps1; python -m discord_codex_bridge --env-file .env`"" /f
```

这只是一个最小示例。实际部署时建议把启动命令收敛到单独脚本里，再让任务调度器调用脚本。

## Design Boundaries

- 服务只处理 `bridges.local.json` 中明确声明的频道，不会把其他频道消息转进终端会话
- 默认行为仍然是“请求转发 + 周期性进度 + 完成摘要”，不会把终端全量实时镜像到 Discord
- 如果目标终端暂时不可解析，服务会记录日志并在后续轮询继续重试，而不是直接丢消息或篡改状态
- `WezTerm` backend 的中断当前通过原始 `ESC` 文本注入实现；如果目标应用对 `ESC` 处理方式不同，实际效果以运行时行为为准
