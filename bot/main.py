from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import aiohttp

from bot import config
from bot.bot import SimulatorBot


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    # Set timeout for all network requests (prevents hanging indefinitely)
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        bot = SimulatorBot(session=session, game_id=config.GAME_ID, token=config.TOKEN, base_url=config.BASE_URL)
        logging.info("web view: %s", bot.web_url)
        await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
