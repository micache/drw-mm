from bot.models import BookLevel, BotState, ContractMeta, OrderBook
from bot.pnl_engine import PnlEngine


def test_compute_mark_price_prefers_last_trade_over_mid() -> None:
    book = OrderBook(
        contract_id="A",
        timestamp=0.0,
        bids=(BookLevel(price=10.0, qty=1),),
        asks=(BookLevel(price=12.0, qty=1),),
    )
    mark, source = PnlEngine.compute_mark_price(book, last_trade=9.5, fv=11.0)
    assert mark == 9.5
    assert source == "last_trade"


def test_position_unrealized_uses_last_trade_mark() -> None:
    state = BotState()
    state.positions_raw["A"] = 2
    state.avg_entry_by_symbol["A"] = 10.0
    state.contracts["A"] = ContractMeta("A", "A", "a")
    state.order_books["A"] = OrderBook(
        contract_id="A",
        timestamp=0.0,
        bids=(BookLevel(price=8.0, qty=1),),
        asks=(BookLevel(price=12.0, qty=1),),
    )
    state.last_trade_by_symbol["A"] = 11.5

    view = PnlEngine().build_position_views(state)[0]

    assert view.mark_price == 11.5
    assert view.mark_price_source == "last_trade"
    assert view.unrealized_pnl == 3.0
