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
class EngineConfig:
    pre_signal: PreSignalConfig = PreSignalConfig()
    reversion: ReversionConfig = ReversionConfig()
    state: StateConfig = StateConfig()
    market_stability: MarketStabilityConfig = MarketStabilityConfig()
    edge: EdgeConfig = EdgeConfig()
    signal: SignalConfig = SignalConfig()


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
    )

