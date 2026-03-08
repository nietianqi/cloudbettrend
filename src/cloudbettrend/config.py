from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PreSignalConfig:
    strong_move_ticks: int = 2
    weak_move_ticks: int = 1
    consensus_threshold: float = 0.7
    close_odds_strength_threshold: float = 1.90
    min_pre_score: int = 3


@dataclass(frozen=True)
class ReversionConfig:
    strong_reversion_ticks: int = 2
    weak_reversion_ticks: int = 1
    prime_window_start: int = 5
    prime_window_end: int = 12
    secondary_window_end: int = 20


@dataclass(frozen=True)
class StateConfig:
    min_dangerous_attacks_ratio_fav: float = 0.40
    min_shots_diff_fav: int = -2
    min_shots_on_target_diff_fav: int = -1
    min_corners_diff_fav: int = -2
    min_total_shots_for_ou_after_12: int = 3
    min_total_dangerous_attacks_for_ou_after_12: int = 20


@dataclass(frozen=True)
class MarketStabilityConfig:
    min_seconds_since_reopen: int = 15
    max_line_jumps_last_60s: int = 2
    max_odds_jumps_last_60s: int = 2
    require_open_status: bool = True
    min_max_stake: float = 0.0


@dataclass(frozen=True)
class EdgeConfig:
    min_edge_after_cost: float = 0.03
    strong_edge: float = 0.04
    medium_edge: float = 0.02
    default_cost_bps: float = 20.0


@dataclass(frozen=True)
class SignalConfig:
    minute_start: int = 3
    minute_end: int = 25
    require_neutral_score: bool = True
    allow_red_cards: bool = False
    min_total_score: int = 6


@dataclass(frozen=True)
class RiskConfig:
    initial_bankroll: float = 100000.0
    max_drawdown_hard: float = 0.25
    daily_loss_limit: float = 0.05
    max_consecutive_losses: int = 6
    max_trades_per_day: int = 40
    max_stake_pct_of_equity: float = 0.02
    max_event_exposure_pct: float = 0.03
    min_stake_pct_of_equity: float = 0.001


@dataclass(frozen=True)
class BankrollConfig:
    fractional_kelly: float = 0.35
    max_fraction_per_bet: float = 0.02
    min_fraction_per_bet: float = 0.001
    absolute_min_stake: float = 0.0
    level_a_multiplier: float = 1.0
    level_b_multiplier: float = 0.75
    level_c_multiplier: float = 0.50
    level_d_multiplier: float = 0.0
    target_volatility: float = 0.015
    vol_lookback: int = 50
    min_vol_samples: int = 8
    min_vol_scale: float = 0.50
    max_vol_scale: float = 1.50
    drawdown_soft_start: float = 0.10
    drawdown_soft_end: float = 0.20
    drawdown_min_scale: float = 0.30
    loss_streak_scale_start: int = 3
    loss_streak_penalty: float = 0.85


@dataclass(frozen=True)
class EngineConfig:
    pre_signal: PreSignalConfig = PreSignalConfig()
    reversion: ReversionConfig = ReversionConfig()
    state: StateConfig = StateConfig()
    market_stability: MarketStabilityConfig = MarketStabilityConfig()
    edge: EdgeConfig = EdgeConfig()
    signal: SignalConfig = SignalConfig()
    risk: RiskConfig = RiskConfig()
    bankroll: BankrollConfig = BankrollConfig()


DEFAULT_CONFIG = EngineConfig()


def _merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _to_dict(config: EngineConfig) -> dict[str, Any]:
    return {
        "pre_signal": vars(config.pre_signal),
        "reversion": vars(config.reversion),
        "state": vars(config.state),
        "market_stability": vars(config.market_stability),
        "edge": vars(config.edge),
        "signal": vars(config.signal),
        "risk": vars(config.risk),
        "bankroll": vars(config.bankroll),
    }


def load_engine_config(path: str | Path | None) -> EngineConfig:
    if path is None:
        return DEFAULT_CONFIG

    config_path = Path(path)
    user_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    base = _to_dict(DEFAULT_CONFIG)
    merged = _merge(base, user_data)

    return EngineConfig(
        pre_signal=PreSignalConfig(**merged["pre_signal"]),
        reversion=ReversionConfig(**merged["reversion"]),
        state=StateConfig(**merged["state"]),
        market_stability=MarketStabilityConfig(**merged["market_stability"]),
        edge=EdgeConfig(**merged["edge"]),
        signal=SignalConfig(**merged["signal"]),
        risk=RiskConfig(**merged["risk"]),
        bankroll=BankrollConfig(**merged["bankroll"]),
    )
