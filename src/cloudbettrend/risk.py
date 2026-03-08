from __future__ import annotations

import datetime
from collections import deque
from dataclasses import dataclass, field

from .config import EngineConfig
from .models import SignalInput


@dataclass
class PortfolioState:
    equity: float
    peak_equity: float
    day_start_equity: float

    # Daily tracking
    current_day: str | None = None
    daily_pnl: float = 0.0
    daily_trades: int = 0
    consecutive_losses: int = 0
    total_trades: int = 0
    blocked_trades: int = 0
    max_drawdown_seen: float = 0.0
    rolling_returns: deque[float] = field(default_factory=lambda: deque(maxlen=500))

    # Weekly tracking
    current_week: str | None = None
    week_start_equity: float = 0.0
    weekly_pnl: float = 0.0

    # Monthly tracking
    current_month: str | None = None
    month_start_equity: float = 0.0
    monthly_pnl: float = 0.0

    # CLV feedback (rolling window for bankroll CLV-based scaling)
    rolling_clv_bps: deque[float] = field(default_factory=lambda: deque(maxlen=200))

    # Correlated market protection: match IDs executed today
    daily_executed_match_ids: set = field(default_factory=set)

    @classmethod
    def create(cls, initial_bankroll: float) -> PortfolioState:
        return cls(
            equity=initial_bankroll,
            peak_equity=initial_bankroll,
            day_start_equity=initial_bankroll,
            week_start_equity=initial_bankroll,
            month_start_equity=initial_bankroll,
        )

    @property
    def drawdown_ratio(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max((self.peak_equity - self.equity) / self.peak_equity, 0.0)

    def ensure_day(self, day_key: str) -> None:
        """Reset daily counters when the day changes; cascade to week/month resets."""
        if self.current_day == day_key:
            return
        self.current_day = day_key
        self.day_start_equity = self.equity
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_executed_match_ids = set()
        # Cascade to week and month so callers only need to call ensure_day
        self._ensure_week(day_key)
        self._ensure_month(day_key)

    def _ensure_week(self, day_key: str) -> None:
        """Reset weekly counters when the ISO week changes."""
        try:
            d = datetime.date.fromisoformat(day_key)
            iso_year, iso_week, _ = d.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
        except ValueError:
            week_key = day_key  # fallback for malformed keys
        if self.current_week == week_key:
            return
        self.current_week = week_key
        self.week_start_equity = self.equity
        self.weekly_pnl = 0.0

    def _ensure_month(self, day_key: str) -> None:
        """Reset monthly counters when the calendar month changes."""
        month_key = day_key[:7]  # "YYYY-MM"
        if self.current_month == month_key:
            return
        self.current_month = month_key
        self.month_start_equity = self.equity
        self.monthly_pnl = 0.0

    def record_trade(
        self,
        pnl: float,
        equity_before: float,
        match_id: str | None = None,
        clv_bps: float | None = None,
    ) -> None:
        self.total_trades += 1
        self.daily_trades += 1
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.monthly_pnl += pnl
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
        # Push/void (pnl == 0): consecutive_losses unchanged — correct behaviour

        # Track executed match IDs for correlated market protection
        if match_id is not None:
            self.daily_executed_match_ids.add(match_id)

        # Record CLV for the bankroll feedback loop
        if clv_bps is not None:
            self.rolling_clv_bps.append(clv_bps)

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
        level: str = "D",
    ) -> RiskDecision:
        """
        Check all risk limits before allowing a trade.

        Args:
            signal: The signal being evaluated.
            state: Current portfolio state.
            proposed_stake: Stake proposed by BankrollManager (in currency units).
            level: Signal quality level (A/B/C/D); used for level-specific stake caps.

        Returns:
            RiskDecision with allowed=True and the final stake, or denied with reason.
        """
        cfg = self.config.risk

        # --- Basic validation ---
        if proposed_stake <= 0:
            return RiskDecision.denied("stake_non_positive")

        # --- Hard drawdown stop ---
        if state.drawdown_ratio >= cfg.max_drawdown_hard:
            return RiskDecision.denied("hard_drawdown_limit_hit")

        # --- Daily loss limit ---
        if state.daily_pnl <= -cfg.daily_loss_limit * max(state.day_start_equity, 1e-9):
            return RiskDecision.denied("daily_loss_limit_hit")

        # --- Weekly loss limit ---
        if state.current_week is not None:
            if state.weekly_pnl <= -cfg.weekly_loss_limit * max(state.week_start_equity, 1e-9):
                return RiskDecision.denied("weekly_loss_limit_hit")

        # --- Monthly loss limit ---
        if state.current_month is not None:
            if state.monthly_pnl <= -cfg.monthly_loss_limit * max(state.month_start_equity, 1e-9):
                return RiskDecision.denied("monthly_loss_limit_hit")

        # --- Consecutive loss guard ---
        if state.consecutive_losses >= cfg.max_consecutive_losses:
            return RiskDecision.denied("max_consecutive_losses_hit")

        # --- Daily trade limit ---
        if state.daily_trades >= cfg.max_trades_per_day:
            return RiskDecision.denied("max_trades_per_day_hit")

        # --- Correlated market protection ---
        match_id = signal.pre.match_id
        existing_count = sum(1 for mid in state.daily_executed_match_ids if mid == match_id)
        if existing_count >= cfg.max_same_match_trades:
            return RiskDecision.denied("same_match_trade_limit_hit")

        # --- Stake cap computation ---
        equity_cap = cfg.max_stake_pct_of_equity * state.equity

        # Level-specific cap: Level C bets capped more conservatively
        if level == "C":
            equity_cap = min(equity_cap, cfg.level_c_max_stake_pct * state.equity)

        event_cap = cfg.max_event_exposure_pct * state.equity
        stake_cap = min(equity_cap, event_cap)

        # Market liquidity cap from exchange
        if signal.live.max_stake is not None:
            stake_cap = min(stake_cap, signal.live.max_stake)

        # Soft drawdown warning: halve stake cap when approaching the hard stop
        if state.drawdown_ratio >= cfg.soft_drawdown_warning:
            stake_cap *= cfg.soft_drawdown_stake_scale

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
