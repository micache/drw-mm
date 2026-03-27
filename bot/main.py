from __future__ import annotations

import argparse
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DRW simulator bot")
    parser.add_argument(
        "--use_betting_odds",
        action="store_true",
        help="Enable external betting-odds polling and live-odds fair value adjustments.",
    )
    return parser.parse_args(argv)


async def main(use_betting_odds: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    async with create_session() as session:
        bot = SimulatorBot(
            session=session,
            game_id=config.GAME_ID,
            token=config.TOKEN,
            base_url=config.BASE_URL,
            use_betting_odds=use_betting_odds,
        )
        logging.info("web view: %s", bot.web_url)
        await bot.start()


if __name__ == "__main__":
    try:
        args = parse_args()
        asyncio.run(main(use_betting_odds=args.use_betting_odds))
    except KeyboardInterrupt:
        logging.info("shutdown requested via Ctrl+C")
