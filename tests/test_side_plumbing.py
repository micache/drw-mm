from bot.simulator_adapter import SimulatorAdapter


class DummyClient:
    async def send_order(self, symbol, price, qty, order_type):
        self.last = (symbol, price, qty, order_type)


def test_signed_qty_side_semantics():
    client = DummyClient()
    adapter = SimulatorAdapter(client)

    import asyncio

    asyncio.run(adapter.place_bid("ABC", 10.0, 3))
    assert client.last[2] == 3

    asyncio.run(adapter.place_ask("ABC", 10.0, 3))
    assert client.last[2] == -3
