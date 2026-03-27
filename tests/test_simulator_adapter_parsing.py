import asyncio

from bot.simulator_adapter import SimulatorAdapter


class DummyClient:
    def __init__(self, fills_payload, account_payload):
        self._fills_payload = fills_payload
        self._account_payload = account_payload
        self.cash = 0.0
        self.margin = 0.0
        self.positions = {}

    async def _get(self, path):
        if path == "fills":
            return self._fills_payload
        if path == "account":
            return self._account_payload
        return {}


def test_sync_fills_accepts_dict_payload_and_side_sign():
    payload = {
        "1": {
            "timestamp": 1,
            "order_id": 10,
            "display_symbol": "A",
            "px": 7.5,
            "quantity": 2,
            "side": "sell",
        }
    }
    adapter = SimulatorAdapter(DummyClient(payload, {}))
    fills = asyncio.run(adapter.sync_fills())
    assert len(fills) == 1
    assert fills[0].traded_qty == -2


def test_sync_account_reads_top_level_avg_entries():
    account = {
        "cash": 10,
        "margin": 0,
        "positions": {"A": {"quantity": 3}},
        "avg_entry_prices": {"A": "6.25"},
    }
    adapter = SimulatorAdapter(DummyClient([], account))
    _, _, positions, _, avgs = asyncio.run(adapter.sync_account())
    assert positions["A"] == 3
    assert avgs["A"] == 6.25


def test_sync_fills_accepts_tuple_rows_payload():
    payload = [[1, 10, "A", 7.5, -2, 0]]
    adapter = SimulatorAdapter(DummyClient(payload, {}))
    fills = asyncio.run(adapter.sync_fills())
    assert len(fills) == 1
    assert fills[0].display_symbol == "A"
    assert fills[0].traded_qty == -2


def test_sync_account_reads_nested_position_stats_avg_entries():
    account = {
        "cash": 10,
        "margin": 0,
        "positions": {"A": {"quantity": -3}},
        "position_stats": {"A": {"entry_price": 6.25}},
    }
    adapter = SimulatorAdapter(DummyClient([], account))
    _, _, positions, _, avgs = asyncio.run(adapter.sync_account())
    assert positions["A"] == -3
    assert avgs["A"] == 6.25


def test_sync_account_reads_avg_entries_with_non_string_symbol_keys():
    account = {
        "cash": 10,
        "margin": 0,
        "positions": [{"display_symbol": "101", "quantity": 2}],
        "avg_entry_prices": {101: "4.5"},
    }
    adapter = SimulatorAdapter(DummyClient([], account))
    _, _, positions, _, avgs = asyncio.run(adapter.sync_account())
    assert positions["101"] == 2
    assert avgs["101"] == 4.5
