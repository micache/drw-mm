from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / "trading-simulator-client"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from trading_client import Client, create_session  # type: ignore


class ForceOrderSmokeBot(Client):
    async def on_start(self) -> None:
        try:
            await self.register()
        except Exception:
            logging.info("register skipped/fail; continuing")

        books = await self.get_order_books()
        if not books:
            logging.error("No books available, cannot place smoke order")
            return

        symbol, book = next(iter(books.items()))
        if book.best_bid_px is not None:
            px = max(0.01, float(book.best_bid_px))
        elif book.best_ask_px is not None:
            px = max(0.01, float(book.best_ask_px) - 0.01)
        else:
            px = 0.01

        qty = 1
        logging.info("Placing smoke BID: symbol=%s px=%s qty=%s", symbol, px, qty)
        order = await self.send_order(symbol, px, qty, "BID")
        logging.info("Placed smoke order id=%s symbol=%s px=%s qty=%s", order.order_id, order.display_symbol, order.px, order.qty)

        await asyncio.sleep(2)
        await self.cancel_orders([int(order.order_id)])
        logging.info("Canceled smoke order id=%s", order.order_id)

        # keep a short window for observing websocket callbacks
        await asyncio.sleep(2)
        raise SystemExit(0)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    game_id = int(os.environ["DRW_GAME_ID"])
    token = os.environ["DRW_TOKEN"]
    base_url = os.getenv("DRW_BASE_URL", "https://games.drw.com")

    async with create_session() as session:
        bot = ForceOrderSmokeBot(session=session, game_id=game_id, token=token, base_url=base_url)
        logging.info("web view: %s", bot.web_url)
        await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
