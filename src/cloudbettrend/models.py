from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MarketType(str, Enum):
    AH = "AH"
    OU = "OU"
    TEAM_TOTAL = "TEAM_TOTAL"
    ONE_X_TWO = "1X2"
    DNB = "DNB"
    DOUBLE_CHANCE = "DOUBLE_CHANCE"
    HALF_TIME = "HALF_TIME"


@dataclass(frozen=True)
class PreMatchSnapshot:
    match_id: str
    league: str
    kickoff_time: str
    home_team: str
    away_team: str
    market_type: MarketType
    open_line: float
    open_odds: float
    close_line: float
    close_odds: float
    line_move_ticks: int | None = None
    odds_move_bps: float | None = None
    consensus_strength: float = 0.0
    close_snapshot_time: str | None = None
    close_price_quality: str = "unknown"


@dataclass(frozen=True)
class LiveMarketSnapshot:
    signal_time: str
    minute: int
    second: int
    score_home: int
    score_away: int
    live_line: float
    live_back_odds: float
    live_lay_odds: float | None = None
    live_spread: float | None = None
    max_stake: float | None = None
    market_status: str = "OPEN"
    seconds_since_reopen: int | None = None
    line_jump_count_last_60s: int = 0
    odds_jump_count_last_60s: int = 0

    @property
    def total_goals(self) -> int:
        return self.score_home + self.score_away


@dataclass(frozen=True)
class MatchStateSnapshot:
    red_home: int = 0
    red_away: int = 0
    yellow_home: int = 0
    yellow_away: int = 0
    shots_home: int = 0
    shots_away: int = 0
    shots_on_target_home: int = 0
    shots_on_target_away: int = 0
    dangerous_attacks_home: int = 0
    dangerous_attacks_away: int = 0
    corners_home: int = 0
    corners_away: int = 0
    possession_home: float | None = None
    possession_away: float | None = None
    attacks_home: int | None = None
    attacks_away: int | None = None
    injury_flag_home: bool = False
    injury_flag_away: bool = False
    favorite_under_heavy_pressure: bool = False
    is_post_suspend_noise: bool = False
    hard_negative_event: bool = False
    market_trending_against_signal: bool = False
    reversion_explained_by_time_decay_only: bool = False

    @property
    def red_cards_total(self) -> int:
        return self.red_home + self.red_away


@dataclass(frozen=True)
class ModelSnapshot:
    fair_prob: float | None = None
    fair_odds: float | None = None
    market_prob: float | None = None
    edge_raw: float | None = None
    edge_after_cost: float | None = None
    cost_bps: float | None = None


@dataclass(frozen=True)
class ExecutionSnapshot:
    intended_stake: float | None = None
    allowed_stake: float | None = None
    placed_odds: float | None = None
    matched_odds: float | None = None
    rejected_flag: bool = False
    slippage_bps: float | None = None
    execution_delay_ms: int | None = None


@dataclass(frozen=True)
class ResultSnapshot:
    final_score_home: int | None = None
    final_score_away: int | None = None
    outcome_winlosepush: str | None = None
    pnl: float | None = None
    closing_line_after_1m: float | None = None
    closing_line_after_3m: float | None = None
    closing_odds_after_1m: float | None = None
    closing_odds_after_3m: float | None = None
    clv_bps: float | None = None


@dataclass(frozen=True)
class SignalInput:
    pre: PreMatchSnapshot
    live: LiveMarketSnapshot
    state: MatchStateSnapshot
    model: ModelSnapshot = field(default_factory=ModelSnapshot)
    execution: ExecutionSnapshot = field(default_factory=ExecutionSnapshot)
    result: ResultSnapshot = field(default_factory=ResultSnapshot)
    favorite_side: str = "home"
    direction: int = 1


@dataclass(frozen=True)
class SignalEvaluation:
    accepted: bool
    reason: str | None
    signal_label: str
    signal_score: int
    level: str
    pre_signal_score: int
    reversion_score: int
    state_score: int
    penalty_score: int
    edge_score: int
    line_move_ticks: int
    reversion_ticks: int
    edge_raw: float
    edge_after_cost: float
    fair_odds: float
    market_stable: bool

