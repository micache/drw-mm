from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from bot import config
from bot.models import BookLevel, ContractMeta, FillView, OrderBook, OrderView

logger = logging.getLogger(__name__)


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
        avg_entries.update(_parse_top_level_avg_entries(data, positions))
        avg_entries.update(_parse_nested_position_avg_entries(data, positions))
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
        fills: list[FillView] = []
        for item in _iter_fill_items(data):
            symbol = str(
                item.get("display_symbol")
                or item.get("displaySymbol")
                or item.get("symbol")
                or item.get("contract_id")
                or item.get("contractId")
                or ""
            )
            if not symbol:
                continue
            ts_raw = item.get("timestamp", item.get("ts", item.get("time")))
            oid_raw = item.get("order_id", item.get("orderId"))
            px_raw = item.get("price", item.get("px"))
            qty_raw = item.get("traded_qty", item.get("tradedQty", item.get("traded_quantity", item.get("quantity", item.get("qty")))))
            if ts_raw is None or oid_raw is None or px_raw is None or qty_raw is None:
                continue

            side = str(item.get("side", "")).lower()
            qty = _to_int(qty_raw)
            if qty is None:
                continue
            if side in {"sell", "ask"} and qty > 0:
                qty = -qty
            if side in {"buy", "bid"} and qty < 0:
                qty = -qty

            timestamp = _to_float(ts_raw)
            order_id = _to_int(oid_raw)
            price = _to_float(px_raw)
            remaining = _to_int(item.get("remaining_qty", item.get("remainingQty", item.get("remaining_quantity", 0))))
            if timestamp is None or order_id is None or price is None or remaining is None:
                continue

            fills.append(
                FillView(
                    timestamp=timestamp,
                    order_id=order_id,
                    display_symbol=symbol,
                    team_name=symbol,
                    price=price,
                    traded_qty=qty,
                    remaining_qty=remaining,
                )
            )

        fills.sort(key=lambda x: (x.timestamp, x.order_id))
        logger.info("sync_fills parsed=%d", len(fills))
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
        if isinstance(value, (int, float, str)):
            parsed = _to_float(value)
            if parsed is not None:
                return parsed
    return None


def _parse_top_level_avg_entries(account: dict[str, Any], positions: dict[str, int]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in (
        "avg_entry_prices",
        "average_entry_prices",
        "avg_prices",
        "avg_entry_price",
        "average_entry_price",
        "entry_prices",
        "position_avg_entry",
        "position_avg_entries",
        "avgEntryPrices",
        "averageEntryPrices",
        "averagePrices",
        "avgPrices",
        "cost_basis",
        "costBasis",
        "avg_cost",
        "avgCost",
        "average_cost",
        "averageCost",
        "avg_px",
        "avgPx",
        "average_px",
        "averagePx",
    ):
        raw = account.get(key)
        if not isinstance(raw, dict):
            continue
        for symbol, value in raw.items():
            sym = str(symbol)
            if sym not in positions:
                continue
            parsed = _to_float(value)
            if parsed is not None and parsed > 0:
                out[sym] = parsed
    return out


def _parse_account_positions(raw_positions: Any) -> tuple[dict[str, int], dict[str, float]]:
    positions: dict[str, int] = {}
    avg_entries: dict[str, float] = {}

    if isinstance(raw_positions, list):
        iterable = []
        for row in raw_positions:
            if isinstance(row, dict):
                sym = row.get("display_symbol") or row.get("displaySymbol") or row.get("symbol") or row.get("contract_id") or row.get("contractId")
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
            qty = _to_int(
                value.get(
                    "qty",
                    value.get(
                        "quantity",
                        value.get(
                            "position",
                            value.get("net_qty", value.get("net_quantity", value.get("signed_qty", 0))),
                        ),
                    ),
                )
            ) or 0
            side = str(value.get("side", "")).lower()
            if qty and side in {"sell", "ask"} and qty > 0:
                qty = -qty
            avg_val = value.get(
                "avg_entry_price",
                value.get(
                    "avgEntryPrice",
                    value.get(
                        "average_entry_price",
                        value.get(
                            "averageEntryPrice",
                            value.get(
                                "average_price",
                                value.get(
                                    "avg_price",
                                    value.get(
                                        "entry_price",
                                        value.get(
                                            "avg_fill_price",
                                            value.get(
                                                "avgFillPrice",
                                                value.get(
                                                    "entryPrice",
                                                    value.get(
                                                        "cost_basis",
                                                        value.get(
                                                            "avg_cost",
                                                            value.get(
                                                                "avgCost",
                                                                value.get(
                                                                    "average_cost",
                                                                    value.get(
                                                                        "averageCost",
                                                                        value.get(
                                                                            "avg_px",
                                                                            value.get(
                                                                                "avgPx",
                                                                                value.get("average_px", value.get("averagePx")),
                                                                            ),
                                                                        ),
                                                                    ),
                                                                ),
                                                            ),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            )
            avg = _to_float(avg_val)
            if avg is None and qty:
                notional = _to_float(
                    value.get(
                        "cost_basis_total",
                        value.get(
                            "position_cost",
                            value.get("position_notional", value.get("notional", value.get("cost_basis"))),
                        ),
                    )
                )
                if notional is not None:
                    avg = abs(notional) / max(1, abs(qty))
        elif isinstance(value, (int, float, str)):
            qty = _to_int(value) or 0

        if qty == 0:
            continue
        positions[str(symbol)] = qty
        if avg is not None and avg > 0:
            avg_entries[str(symbol)] = avg
    return positions, avg_entries


def _parse_nested_position_avg_entries(account: dict[str, Any], positions: dict[str, int]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in (
        "position_stats",
        "positions_meta",
        "positionStats",
        "positionsMeta",
        "position_costs",
        "positionCosts",
    ):
        raw = account.get(key)
        if not isinstance(raw, dict):
            continue
        for symbol, payload in raw.items():
            sym = str(symbol)
            if sym not in positions:
                continue
            avg: float | None = None
            if isinstance(payload, dict):
                avg = _to_float(
                    payload.get(
                        "avg_entry_price",
                        payload.get(
                            "avgEntryPrice",
                            payload.get(
                                "average_entry_price",
                                payload.get(
                                    "averageEntryPrice",
                                    payload.get(
                                        "avg_price",
                                        payload.get(
                                            "entry_price",
                                            payload.get(
                                                "entryPrice",
                                                payload.get(
                                                    "avg_cost",
                                                    payload.get(
                                                        "avgCost",
                                                        payload.get(
                                                            "average_cost",
                                                            payload.get(
                                                                "averageCost",
                                                                payload.get("avg_px", payload.get("avgPx")),
                                                            ),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    )
                )
            else:
                avg = _to_float(payload)
            if avg is not None and avg > 0:
                out[sym] = avg
    return out


def _iter_fill_items(data: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if isinstance(data.get("fills"), list):
            data = data["fills"]
        elif all(isinstance(v, dict) for v in data.values()):
            data = list(data.values())

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                out.append(item)
                continue
            # tolerate tuple/list payloads:
            # [timestamp, order_id, display_symbol, price, traded_qty, remaining_qty]
            if isinstance(item, (list, tuple)) and len(item) >= 5:
                out.append(
                    {
                        "timestamp": item[0],
                        "order_id": item[1],
                        "display_symbol": item[2],
                        "price": item[3],
                        "traded_qty": item[4],
                        "remaining_qty": item[5] if len(item) > 5 else 0,
                    }
                )
    return out


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
