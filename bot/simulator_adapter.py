from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from bot import config
from bot.models import BookLevel, ContractMeta, FillView, OrderBook, OrderView


@dataclass
class SimulatorAdapter:
    client: Any

    async def sync_account(self) -> tuple[float, float, dict[str, int], float | None, dict[str, float]]:
        try:
            data = await self.client._get("account")
        except Exception:
            await self.client.update_positions()
            return self.client.cash, self.client.margin, dict(self.client.positions), None, {}

        cash = float(data.get("cash", 0.0))
        margin = float(data.get("margin", 0.0))
        positions, avg_entries = _parse_account_positions(data.get("positions", {}))
        total_pnl = _extract_total_pnl(data)
        self.client.cash = cash
        self.client.margin = margin
        self.client.positions = positions
        return cash, margin, positions, total_pnl, avg_entries

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

    async def sync_fills(self) -> list[FillView]:
        data = await self.client._get("fills")
        if not isinstance(data, list):
            return []
        fills: list[FillView] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("display_symbol") or item.get("symbol") or "")
            if not symbol:
                continue
            ts_raw = item.get("timestamp")
            if ts_raw is None:
                continue
            px_raw = item.get("price", item.get("px"))
            qty_raw = item.get("traded_qty", item.get("traded_quantity", item.get("quantity")))
            oid_raw = item.get("order_id")
            if px_raw is None or qty_raw is None or oid_raw is None:
                continue
            try:
                fills.append(
                    FillView(
                        timestamp=float(ts_raw),
                        order_id=int(oid_raw),
                        display_symbol=symbol,
                        team_name=symbol,
                        price=float(px_raw),
                        traded_qty=int(qty_raw),
                        remaining_qty=int(item.get("remaining_qty", item.get("remaining_quantity", 0))),
                    )
                )
            except (TypeError, ValueError):
                continue
        fills.sort(key=lambda x: (x.timestamp, x.order_id))
        return fills

    async def sync_order_books(self) -> dict[str, OrderBook]:
        raw = await self.client.get_order_books()
        out: dict[str, OrderBook] = {}
        for symbol, book in raw.items():
            bids = tuple(BookLevel(price=p, qty=q) for p, q in sorted(book.bids.items(), reverse=True))
            asks = tuple(BookLevel(price=p, qty=q) for p, q in sorted(book.asks.items()))
            out[symbol] = OrderBook(contract_id=symbol, timestamp=book.timestamp, bids=bids, asks=asks)
        return out

    async def place_bid(self, symbol: str, price: float, qty: int) -> None:
        await self.client.send_order(symbol, price, abs(qty), config.ORDER_TYPE)

    async def place_ask(self, symbol: str, price: float, qty: int) -> None:
        await self.client.send_order(symbol, price, -abs(qty), config.ORDER_TYPE)

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


def _extract_total_pnl(account: dict[str, Any]) -> float | None:
    for key in ("total_pnl", "pnl_total", "pnl", "mark_to_market_pnl", "mtm_pnl"):
        value = account.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _parse_account_positions(raw_positions: Any) -> tuple[dict[str, int], dict[str, float]]:
    positions: dict[str, int] = {}
    avg_entries: dict[str, float] = {}

    if isinstance(raw_positions, list):
        iterable = []
        for row in raw_positions:
            if isinstance(row, dict):
                sym = row.get("display_symbol") or row.get("symbol")
                if sym is not None:
                    iterable.append((str(sym), row))
    elif isinstance(raw_positions, dict):
        iterable = list(raw_positions.items())
    else:
        return positions, avg_entries

    for symbol, value in iterable:
        qty = 0
        avg: float | None = None
        if isinstance(value, dict):
            qty = int(value.get("qty", value.get("quantity", value.get("position", 0))))
            avg_val = value.get(
                "avg_entry_price",
                value.get("average_entry_price", value.get("average_price", value.get("avg_price", value.get("cost_basis")))),
            )
            if isinstance(avg_val, (int, float)):
                avg = float(avg_val)
        elif isinstance(value, (int, float)):
            qty = int(value)

        if qty == 0:
            continue
        positions[str(symbol)] = qty
        if avg is not None and avg > 0:
            avg_entries[str(symbol)] = avg
    return positions, avg_entries
