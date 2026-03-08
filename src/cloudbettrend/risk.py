from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .config import EngineConfig
from .models import SignalInput


@dataclass
class PortfolioState:
    equity: float
    peak_equity: float
    day_start_equity: float
    current_day: str | None = None
    daily_pnl: float = 0.0
    daily_trades: int = 0
    consecutive_losses: int = 0
    total_trades: int = 0
    blocked_trades: int = 0
    max_drawdown_seen: float = 0.0
    rolling_returns: deque[float] = field(default_factory=lambda: deque(maxlen=500))

    @classmethod
    def create(cls, initial_bankroll: float) -> PortfolioState:
        return cls(
            equity=initial_bankroll,
            peak_equity=initial_bankroll,
            day_start_equity=initial_bankroll,
        )

    @property
    def drawdown_ratio(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max((self.peak_equity - self.equity) / self.peak_equity, 0.0)

    def ensure_day(self, day_key: str) -> None:
        if self.current_day == day_key:
            return
        self.current_day = day_key
        self.day_start_equity = self.equity
        self.daily_pnl = 0.0
        self.daily_trades = 0

    def record_trade(self, pnl: float, equity_before: float) -> None:
        self.total_trades += 1
        self.daily_trades += 1
        self.daily_pnl += pnl
        self.equity += pnl
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        drawdown = self.drawdown_ratio
        if drawdown > self.max_drawdown_seen:
            self.max_drawdown_seen = drawdown

        base = equity_before if equity_before > 1e-9 else 1e-9
        self.rolling_returns.append(pnl / base)

        if pnl < 0:
            self.consecutive_losses += 1
        elif pnl > 0:
            self.consecutive_losses = 0

    def record_blocked(self) -> None:
        self.blocked_trades += 1


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str | None
    stake_after_limits: float
    stake_cap: float

    @classmethod
    def denied(cls, reason: str) -> RiskDecision:
        return cls(allowed=False, reason=reason, stake_after_limits=0.0, stake_cap=0.0)


class RiskManager:
    def __init__(self, config: EngineConfig):
        self.config = config

    def pre_trade_check(
        self,
        signal: SignalInput,
        state: PortfolioState,
        proposed_stake: float,
    ) -> RiskDecision:
        cfg = self.config.risk

        if proposed_stake <= 0:
            return RiskDecision.denied("stake_non_positive")

        if state.drawdown_ratio >= cfg.max_drawdown_hard:
            return RiskDecision.denied("hard_drawdown_limit_hit")

        if state.daily_pnl <= -cfg.daily_loss_limit * max(state.day_start_equity, 1e-9):
            return RiskDecision.denied("daily_loss_limit_hit")

        if state.consecutive_losses >= cfg.max_consecutive_losses:
            return RiskDecision.denied("max_consecutive_losses_hit")

        if state.daily_trades >= cfg.max_trades_per_day:
            return RiskDecision.denied("max_trades_per_day_hit")

        equity_cap = cfg.max_stake_pct_of_equity * state.equity
        event_cap = cfg.max_event_exposure_pct * state.equity
        stake_cap = min(equity_cap, event_cap)
        if signal.live.max_stake is not None:
            stake_cap = min(stake_cap, signal.live.max_stake)

        if stake_cap <= 0:
            return RiskDecision.denied("stake_cap_non_positive")

        min_stake = cfg.min_stake_pct_of_equity * state.equity
        stake_after_limits = min(proposed_stake, stake_cap)

        if stake_after_limits < min_stake:
            return RiskDecision.denied("stake_below_minimum")

        return RiskDecision(
            allowed=True,
            reason=None,
            stake_after_limits=stake_after_limits,
            stake_cap=stake_cap,
        )

