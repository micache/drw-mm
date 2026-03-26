from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


TeamStatus = Literal["alive", "eliminated"]


@dataclass(frozen=True)
class Contract:
    contract_id: str
    team_name: str
    normalized_team_name: str


@dataclass(frozen=True)
class BookLevel:
    price: float
    qty: int


@dataclass(frozen=True)
class OrderBook:
    contract_id: str
    timestamp: float | None
    bids: tuple[BookLevel, ...] = ()
    asks: tuple[BookLevel, ...] = ()

    @property
    def best_bid(self) -> BookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> BookLevel | None:
        return self.asks[0] if self.asks else None


@dataclass(frozen=True)
class Position:
    contract_id: str
    qty: int
    avg_entry_price: float = 0.0


@dataclass(frozen=True)
class OpenOrder:
    order_id: int
    contract_id: str
    side: Literal["buy", "sell"]
    price: float
    qty: int


@dataclass(frozen=True)
class Fill:
    timestamp: float
    order_id: int
    contract_id: str
    price: float
    qty: int


@dataclass(frozen=True)
class FairValue:
    contract_id: str
    value: float
    source: str
    updated_at: float


@dataclass(frozen=True)
class BracketState:
    team_name: str
    normalized_team_name: str
    status: TeamStatus
    current_round: str | None
    eliminated_round: str | None
    settlement_if_known: float | None


@dataclass(frozen=True)
class GameState:
    team_a: str
    team_b: str
    p_team_a: float
    p_team_b: float
    timestamp: float
    bookmaker_count: int
    confidence: str


@dataclass(frozen=True)
class ContractMeta:
    display_symbol: str
    team_name: str
    normalized_team_name: str
    seed: str | None = None
    region: str | None = None
    mapping_status: str = "resolved"
    trading_blocked: bool = False


@dataclass(frozen=True)
class PositionView:
    display_symbol: str
    team_name: str
    qty: int
    avg_entry_price: float | None
    entry_source: str
    best_bid: float | None
    best_ask: float | None
    mark_price: float | None
    mark_price_source: str
    fair_value: float | None
    fair_value_source_timestamp: float | None
    settlement_if_known: float | None
    unrealized_pnl: float | None
    realized_pnl: float
    status: str
    current_round: str | None
    fv_mode: str | None
    mapping_status: str
    ncaa_status_mode: str
    odds_quality_score: float | None
    signal_buy_edge: float | None
    signal_sell_edge: float | None
    last_strategy_reason: str | None
    last_updated_ts: float


@dataclass(frozen=True)
class OrderView:
    order_id: int
    display_symbol: str
    team_name: str
    side: str
    price: float
    qty_signed: int
    qty_abs: int
    canceled: bool
    last_updated_ts: float


@dataclass(frozen=True)
class FillView:
    timestamp: float
    order_id: int
    display_symbol: str
    team_name: str
    price: float
    traded_qty: int
    remaining_qty: int


@dataclass(frozen=True)
class TeamTournamentState:
    team_name: str
    normalized_team_name: str
    alive: bool
    in_live_game: bool
    has_upcoming_game: bool = False
    current_round: str | None = None
    game_id: str | None = None
    eliminated_round: str | None = None
    fixed_settlement: float | None = None
    ncaa_status_mode: str = "unresolved"
    last_status_ts: float = 0.0


@dataclass(frozen=True)
class TeamProbabilities:
    team_name: str
    normalized_team_name: str
    p_r32: float
    p_s16: float
    p_e8: float
    p_f4: float
    p_final: float
    p_champion: float
    baseline_fv: float
    source_timestamp: float
    parsed_ok: bool = True
    raw_team_name: str | None = None
    canonical_team_name: str | None = None


@dataclass(frozen=True)
class LiveGameProb:
    game_id: str
    home_team_normalized: str
    away_team_normalized: str
    home_win_prob: float
    away_win_prob: float
    bookmakers_used: int
    source_timestamp: float
    is_fresh: bool
    is_live: bool = False
    odds_quality_score: float = 0.0
    median_staleness_seconds: float | None = None
    delta_home_win_prob: float = 0.0


@dataclass(frozen=True)
class TeamFairValue:
    display_symbol: str
    team_name: str
    baseline_fv: float
    live_fv: float | None
    pregame_fv: float | None
    active_fv: float
    fixed_settlement: float | None
    fv_mode: str
    source_timestamp: float


@dataclass
class BotState:
    cash: float = 0.0
    margin: float = 0.0
    initial_cash: float | None = None
    server_total_pnl: float | None = None
    positions_raw: dict[str, int] = field(default_factory=dict)
    open_orders: dict[int, OrderView] = field(default_factory=dict)
    fills: list[FillView] = field(default_factory=list)
    contracts: dict[str, ContractMeta] = field(default_factory=dict)
    order_books: dict[str, OrderBook] = field(default_factory=dict)
    team_states: dict[str, TeamTournamentState] = field(default_factory=dict)
    team_probs: dict[str, TeamProbabilities] = field(default_factory=dict)
    live_game_probs: dict[str, LiveGameProb] = field(default_factory=dict)
    fair_values: dict[str, TeamFairValue] = field(default_factory=dict)
    unresolved_symbols: set[str] = field(default_factory=set)
    realized_pnl_by_symbol: dict[str, float] = field(default_factory=dict)
    avg_entry_by_symbol: dict[str, float] = field(default_factory=dict)
    entry_source_by_symbol: dict[str, str] = field(default_factory=dict)
    dirty_flags: set[str] = field(default_factory=set)
    source_timestamps: dict[str, float] = field(default_factory=dict)
    last_trade_by_symbol: dict[str, float] = field(default_factory=dict)
    signal_edges_by_symbol: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    last_strategy_reason_by_symbol: dict[str, str] = field(default_factory=dict)

    def mark_dirty(self, key: str) -> None:
        self.dirty_flags.add(key)

    def set_source_timestamp(self, source: str, ts: float) -> None:
        self.source_timestamps[source] = ts

    def source_age(self, source: str, now: float) -> float:
        return now - self.source_timestamps.get(source, 0.0)
