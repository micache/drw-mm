from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from bot import config
from bot.models import BookLevel, ContractMeta, FillView, OrderBook, OrderView


@dataclass
class SimulatorAdapter:
    client: Any

    async def bootstrap(self) -> tuple[dict[str, int], dict[int, OrderView], dict[str, OrderBook]]:
        await self.client.update_positions()
        await self.client.update_order_books()
        await self.client.update_notifications()
        positions = dict(self.client.positions)
        orders = await self.sync_open_orders()
        books = await self.sync_order_books()
        return positions, orders, books

    async def sync_positions(self) -> dict[str, int]:
        await self.client.update_positions()
        return dict(self.client.positions)

    async def sync_open_orders(self) -> dict[int, OrderView]:
        raw = await self.client.get_open_orders()
        now = time.time()
        out: dict[int, OrderView] = {}
        for oid, order in raw.items():
            side = "buy" if order.qty > 0 else "sell"
            out[oid] = OrderView(
                order_id=oid,
                display_symbol=order.display_symbol,
                team_name=order.display_symbol,
                side=side,
                price=order.px,
                qty_signed=order.qty,
                qty_abs=abs(order.qty),
                canceled=False,
                last_updated_ts=now,
            )
        return out

    async def sync_order_books(self) -> dict[str, OrderBook]:
        raw = await self.client.get_order_books()
        out: dict[str, OrderBook] = {}
        for symbol, book in raw.items():
            bids = tuple(BookLevel(price=p, qty=q) for p, q in sorted(book.bids.items(), reverse=True))
            asks = tuple(BookLevel(price=p, qty=q) for p, q in sorted(book.asks.items()))
            out[symbol] = OrderBook(contract_id=symbol, timestamp=book.timestamp, bids=bids, asks=asks)
        return out

    async def place_bid(self, symbol: str, price: float, qty: int) -> None:
        await self.client.send_order(symbol, price, qty, config.ORDER_TYPE)

    async def place_ask(self, symbol: str, price: float, qty: int) -> None:
        await self.client.send_order(symbol, price, qty, config.ORDER_TYPE)

    async def cancel_order_ids(self, order_ids: list[int]) -> None:
        await self.client.cancel_orders(order_ids)

    async def purge_symbol(self, symbol: str) -> None:
        await self.client.purge_display_symbol(symbol)

    @staticmethod
    def fill_from_ws(fill: Any) -> FillView:
        return FillView(
            timestamp=fill.timestamp,
            order_id=int(fill.order_id),
            display_symbol=fill.display_symbol,
            team_name=fill.display_symbol,
            price=fill.px,
            traded_qty=fill.traded_qty,
            remaining_qty=fill.remaining_qty,
        )

    @staticmethod
    def contracts_from_books(books: dict[str, OrderBook]) -> dict[str, ContractMeta]:
        return {
            symbol: ContractMeta(
                display_symbol=symbol,
                team_name=symbol,
                normalized_team_name=symbol.lower().replace("_", " ").replace("-", " ").strip(),
            )
            for symbol in books
        }
