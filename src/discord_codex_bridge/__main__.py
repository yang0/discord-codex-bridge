from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from discord_codex_bridge.config import Settings, load_env_file
from discord_codex_bridge.service import DiscordCodexBridge


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Discord <-> tmux Codex bridge")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    args = parser.parse_args()

    env_file = Path(args.env_file).expanduser().resolve()
    base_dir = env_file.parent if env_file.exists() else Path.cwd()
    env: dict[str, str] = {}
    load_env_file(env_file, env)
    for key, value in os.environ.items():
        env.setdefault(key, value)
    settings = Settings.from_env(env, base_dir=base_dir)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = DiscordCodexBridge(settings)
    client.run(settings.discord_bot_token, log_handler=None)


if __name__ == "__main__":
    main()
