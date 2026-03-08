from __future__ import annotations

import math
from dataclasses import dataclass

from .config import EngineConfig
from .models import SignalEvaluation, SignalInput
from .risk import PortfolioState


@dataclass(frozen=True)
class BankrollDecision:
    stake: float
    stake_fraction: float
    full_kelly_fraction: float
    volatility_scale: float
    drawdown_scale: float
    level_scale: float
    streak_scale: float
    reason: str | None = None

    @classmethod
    def empty(cls, reason: str) -> BankrollDecision:
        return cls(
            stake=0.0,
            stake_fraction=0.0,
            full_kelly_fraction=0.0,
            volatility_scale=1.0,
            drawdown_scale=1.0,
            level_scale=0.0,
            streak_scale=1.0,
            reason=reason,
        )


class BankrollManager:
    def __init__(self, config: EngineConfig):
        self.config = config

    def _full_kelly_fraction(self, fair_odds: float, market_odds: float) -> float:
        if fair_odds <= 1.0 or market_odds <= 1.0:
            return 0.0
        p = 1.0 / fair_odds
        b = market_odds - 1.0
        if b <= 0:
            return 0.0
        f = (p * market_odds - 1.0) / b
        return max(f, 0.0)

    def _level_scale(self, level: str) -> float:
        cfg = self.config.bankroll
        mapping = {
            "A": cfg.level_a_multiplier,
            "B": cfg.level_b_multiplier,
            "C": cfg.level_c_multiplier,
            "D": cfg.level_d_multiplier,
        }
        return mapping.get(level, cfg.level_d_multiplier)

    def _volatility_scale(self, state: PortfolioState) -> float:
        cfg = self.config.bankroll
        values = list(state.rolling_returns)[-cfg.vol_lookback :]
        if len(values) < cfg.min_vol_samples:
            return 1.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        realized_vol = math.sqrt(max(variance, 0.0))
        if realized_vol <= 1e-8:
            return cfg.max_vol_scale

        scale = cfg.target_volatility / realized_vol
        return min(max(scale, cfg.min_vol_scale), cfg.max_vol_scale)

    def _drawdown_scale(self, state: PortfolioState) -> float:
        cfg = self.config.bankroll
        dd = state.drawdown_ratio
        if dd <= cfg.drawdown_soft_start:
            return 1.0
        if dd >= cfg.drawdown_soft_end:
            return cfg.drawdown_min_scale

        span = max(cfg.drawdown_soft_end - cfg.drawdown_soft_start, 1e-9)
        alpha = (dd - cfg.drawdown_soft_start) / span
        return 1.0 - alpha * (1.0 - cfg.drawdown_min_scale)

    def _streak_scale(self, state: PortfolioState) -> float:
        cfg = self.config.bankroll
        losses = state.consecutive_losses
        if losses < cfg.loss_streak_scale_start:
            return 1.0
        extra = losses - cfg.loss_streak_scale_start + 1
        return cfg.loss_streak_penalty**extra

    def propose_stake(
        self,
        signal: SignalInput,
        evaluation: SignalEvaluation,
        state: PortfolioState,
    ) -> BankrollDecision:
        if not evaluation.accepted:
            return BankrollDecision.empty("signal_not_accepted")

        full_kelly = self._full_kelly_fraction(
            fair_odds=evaluation.fair_odds,
            market_odds=signal.live.live_back_odds,
        )
        if full_kelly <= 0:
            return BankrollDecision.empty("kelly_non_positive")

        cfg = self.config.bankroll
        level_scale = self._level_scale(evaluation.level)
        if level_scale <= 0:
            return BankrollDecision.empty("level_scale_zero")

        vol_scale = self._volatility_scale(state)
        dd_scale = self._drawdown_scale(state)
        streak_scale = self._streak_scale(state)

        stake_fraction = (
            full_kelly
            * cfg.fractional_kelly
            * level_scale
            * vol_scale
            * dd_scale
            * streak_scale
        )
        stake_fraction = min(max(stake_fraction, 0.0), cfg.max_fraction_per_bet)
        if 0 < stake_fraction < cfg.min_fraction_per_bet:
            stake_fraction = cfg.min_fraction_per_bet

        stake = stake_fraction * state.equity
        if stake < cfg.absolute_min_stake:
            return BankrollDecision.empty("stake_below_absolute_min")

        return BankrollDecision(
            stake=stake,
            stake_fraction=stake_fraction,
            full_kelly_fraction=full_kelly,
            volatility_scale=vol_scale,
            drawdown_scale=dd_scale,
            level_scale=level_scale,
            streak_scale=streak_scale,
            reason=None,
        )

