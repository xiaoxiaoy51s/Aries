"""Bot 子进程入口：在独立进程中运行 QQ/微信/飞书 bot，避免 lark-oapi 等重型 SDK 导入阻塞 FastAPI 主进程。"""

from __future__ import annotations

import logging
import sys
import time


def main(email: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [BotProcess] %(message)s",
    )
    log = logging.getLogger("bot_process")

    from app.services.bot_manager import start_all_bots, stop_all_bots

    log.info("启动 bot 子进程 user=%s", email)
    started = start_all_bots(email)
    log.info("bot 启动结果: %s", started)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("停止 bot 子进程")
        stop_all_bots()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m app.services.bot_process <user_email>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
