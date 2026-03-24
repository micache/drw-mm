from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from bot import config
from bot.bot import SimulatorBot

ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "trading-simulator-client"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from trading_client import create_session  # type: ignore


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    async with create_session() as session:
        bot = SimulatorBot(session=session, game_id=config.GAME_ID, token=config.TOKEN, base_url=config.BASE_URL)
        logging.info("web view: %s", bot.web_url)
        await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("shutdown requested via Ctrl+C")
