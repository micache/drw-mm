from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from bot.models import Fill, OpenOrder, OrderBook
from bot.normalize import normalize_team_name
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = ROOT / 'trading-simulator-client'
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from trading_client import Client as BaseClient  # type: ignore
from trading_client import create_session  # type: ignore

logger = logging.getLogger(__name__)


class SimulatorClient(BaseClient):
    def __init__(self, session: aiohttp.ClientSession, game_id: int, token: str, base_url: str) -> None:
        super().__init__(session=session, game_id=game_id, token=token, base_url=base_url)
        self.book_update_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.fill_queue: asyncio.Queue[list[Fill]] = asyncio.Queue()
        self.order_queue: asyncio.Queue[Any] = asyncio.Queue()
        self.account_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def get_contracts(self) -> dict[str, dict[str, Any]]:
        try:
            data = await self._get("contracts")
        except Exception:
            books = await self.get_order_books()
            return {
                symbol: {
                    "contract_id": symbol,
                    "team_name": symbol,
                    "normalized_team_name": normalize_team_name(symbol),
                }
                for symbol in books
            }

        contracts: dict[str, dict[str, Any]] = {}
        if isinstance(data, list):
            for row in data:
                symbol = row.get("display_symbol") or row.get("symbol")
                if not symbol:
                    continue
                contracts[symbol] = {
                    "contract_id": symbol,
                    "team_name": row.get("team_name", symbol),
                    "normalized_team_name": normalize_team_name(row.get("team_name", symbol)),
                }
        elif isinstance(data, dict):
            for symbol, row in data.items():
                contracts[symbol] = {
                    "contract_id": symbol,
                    "team_name": row.get("team_name", symbol) if isinstance(row, dict) else symbol,
                    "normalized_team_name": normalize_team_name(
                        row.get("team_name", symbol) if isinstance(row, dict) else symbol,
                    ),
                }
        return contracts

    async def get_positions_snapshot(self) -> dict[str, int]:
        await self.update_positions()
        return dict(self.positions)

    async def get_fills(self) -> list[Fill]:
        data = await self._get("fills")
        fills: list[Fill] = []
        if isinstance(data, list):
            for item in data:
                fills.append(
                    Fill(
                        timestamp=float(item.get("timestamp", time.time())),
                        order_id=int(item.get("order_id", 0)),
                        contract_id=item.get("display_symbol", ""),
                        price=float(item.get("price", 0.0)),
                        qty=int(item.get("traded_quantity", item.get("quantity", 0))),
                    )
                )
        return fills

    async def place_order(
        self,
        contract_id: str,
        side: str,
        price: float,
        qty: int,
        tif: str = "GTC",
        post_only: bool = False,
    ) -> OpenOrder:
        order_type = "BID" if side == "buy" else "ASK"
        if post_only:
            logger.debug("post_only requested but simulator API may ignore it")
        _ = tif
        return await self.send_order(display_symbol=contract_id, px=price, qty=qty, order_type=order_type)

    async def cancel_order(self, order_id: int) -> None:
        await self.cancel_orders([order_id])

    async def cancel_all(self, contract_id: str | None = None) -> None:
        if contract_id:
            await self.purge_display_symbol(contract_id)
            return
        await self.purge_all()

    async def on_fills(self, new_fills: list[Fill]) -> None:
        await self.fill_queue.put(new_fills)

    async def on_orderbook_updates(self, order_books: dict[str, OrderBook]) -> None:
        await self.book_update_queue.put(order_books)

    async def on_order_update(self, order: Any) -> None:
        await self.order_queue.put(order)


def make_session() -> aiohttp.ClientSession:
    return create_session()
