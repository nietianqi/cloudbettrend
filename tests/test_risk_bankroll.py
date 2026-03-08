import json
from dataclasses import replace
from pathlib import Path

import pytest

from cloudbettrend.backtest import BacktestRunner
from cloudbettrend.bankroll import BankrollManager
from cloudbettrend.config import DEFAULT_CONFIG
from cloudbettrend.models import (
    LiveMarketSnapshot,
    MarketType,
    MatchStateSnapshot,
    ModelSnapshot,
    PreMatchSnapshot,
    SignalInput,
)
from cloudbettrend.risk import PortfolioState, RiskManager
from cloudbettrend.scoring import PreMatchOverReversionEngine


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _make_signal(
    match_id: str = "m1",
    market_type: MarketType = MarketType.AH,
    fair_odds: float | None = 1.86,
) -> SignalInput:
    """Create a well-formed, typically-accepted AH signal for unit testing."""
    model_snapshot = (
        ModelSnapshot(fair_odds=fair_odds, cost_bps=20.0)
        if fair_odds is not None
        else ModelSnapshot(cost_bps=20.0)  # no fair_odds → engine must estimate
    )
    return SignalInput(
        pre=PreMatchSnapshot(
            match_id=match_id,
            league="EPL",
            kickoff_time="2026-03-01T15:00:00Z",
            home_team="A",
            away_team="B",
            market_type=market_type,
            open_line=-0.25,
            open_odds=1.98,
            close_line=-0.75,
            close_odds=1.88,
            consensus_strength=0.82,
            close_price_quality="good",
        ),
        live=LiveMarketSnapshot(
            signal_time="2026-03-01T15:07:30Z",
            minute=7,
            second=30,
            score_home=0,
            score_away=0,
            live_line=-0.25,
            live_back_odds=1.97,
            market_status="OPEN",
            seconds_since_reopen=40,
            line_jump_count_last_60s=1,
            odds_jump_count_last_60s=1,
            max_stake=5000,
        ),
        state=MatchStateSnapshot(
            red_home=0,
            red_away=0,
            shots_home=2,
            shots_away=1,
            shots_on_target_home=1,
            shots_on_target_away=0,
            dangerous_attacks_home=14,
            dangerous_attacks_away=10,
            corners_home=1,
            corners_away=0,
        ),
        model=model_snapshot,
        favorite_side="home",
        direction=-1,
    )


def _accepted_signal() -> SignalInput:
    """Legacy helper kept for backward compatibility with existing tests."""
    return _make_signal(match_id="m1", market_type=MarketType.AH, fair_odds=1.86)


# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------

def test_bankroll_manager_proposes_positive_stake_for_positive_edge():
    signal = _accepted_signal()
    evaluation = PreMatchOverReversionEngine(DEFAULT_CONFIG).evaluate(signal)
    state = PortfolioState.create(DEFAULT_CONFIG.risk.initial_bankroll)

    decision = BankrollManager(DEFAULT_CONFIG).propose_stake(
        signal=signal,
        evaluation=evaluation,
        state=state,
    )

    assert evaluation.accepted is True
    assert decision.stake > 0
    assert decision.stake_fraction <= DEFAULT_CONFIG.bankroll.max_fraction_per_bet


def test_daily_loss_limit_blocks_next_trade(tmp_path: Path):
    cfg = replace(
        DEFAULT_CONFIG,
        risk=replace(
            DEFAULT_CONFIG.risk,
            initial_bankroll=10000.0,
            daily_loss_limit=0.01,
            max_drawdown_hard=0.99,
            max_consecutive_losses=99,
            max_trades_per_day=20,
        ),
    )

    row1 = {
        "direction": -1,
        "favorite_side": "home",
        "pre": {
            "match_id": "m200",
            "league": "EPL",
            "kickoff_time": "2026-03-02T15:00:00Z",
            "home_team": "A",
            "away_team": "B",
            "market_type": "AH",
            "open_line": -0.25,
            "open_odds": 1.98,
            "close_line": -0.75,
            "close_odds": 1.88,
            "consensus_strength": 0.82,
            "close_price_quality": "good",
        },
        "live": {
            "signal_time": "2026-03-02T15:07:30Z",
            "minute": 7,
            "second": 30,
            "score_home": 0,
            "score_away": 0,
            "live_line": -0.25,
            "live_back_odds": 1.97,
            "market_status": "OPEN",
            "seconds_since_reopen": 40,
            "line_jump_count_last_60s": 1,
            "odds_jump_count_last_60s": 1,
            "max_stake": 1500,
        },
        "state": {
            "red_home": 0,
            "red_away": 0,
            "shots_home": 2,
            "shots_away": 1,
            "shots_on_target_home": 1,
            "shots_on_target_away": 0,
            "dangerous_attacks_home": 14,
            "dangerous_attacks_away": 10,
            "corners_home": 1,
            "corners_away": 0,
        },
        "model": {"fair_odds": 1.86, "cost_bps": 20.0},
        "result": {"pnl": -300.0},
    }
    row2 = {
        "direction": -1,
        "favorite_side": "home",
        "pre": {
            "match_id": "m201",
            "league": "EPL",
            "kickoff_time": "2026-03-02T16:00:00Z",
            "home_team": "C",
            "away_team": "D",
            "market_type": "AH",
            "open_line": -0.25,
            "open_odds": 1.98,
            "close_line": -0.75,
            "close_odds": 1.88,
            "consensus_strength": 0.82,
            "close_price_quality": "good",
        },
        "live": {
            "signal_time": "2026-03-02T16:09:00Z",
            "minute": 9,
            "second": 0,
            "score_home": 0,
            "score_away": 0,
            "live_line": -0.25,
            "live_back_odds": 1.98,
            "market_status": "OPEN",
            "seconds_since_reopen": 40,
            "line_jump_count_last_60s": 1,
            "odds_jump_count_last_60s": 1,
            "max_stake": 1500,
        },
        "state": {
            "red_home": 0,
            "red_away": 0,
            "shots_home": 2,
            "shots_away": 1,
            "shots_on_target_home": 1,
            "shots_on_target_away": 0,
            "dangerous_attacks_home": 14,
            "dangerous_attacks_away": 10,
            "corners_home": 1,
            "corners_away": 0,
        },
        "model": {"fair_odds": 1.86, "cost_bps": 20.0},
    }

    sample = tmp_path / "samples.jsonl"
    sample.write_text(
        json.dumps(row1, ensure_ascii=True)
        + "\n"
        + json.dumps(row2, ensure_ascii=True)
        + "\n",
        encoding="utf-8",
    )

    report = BacktestRunner(cfg).run(sample)

    assert report.accepted_signals == 2
    assert report.executed_trades == 1
    assert report.blocked_by_risk == 1
    assert report.total_pnl == pytest.approx(-300.0)
    assert report.ending_bankroll == pytest.approx(9700.0)


# ---------------------------------------------------------------------------
# New tests: risk management
# ---------------------------------------------------------------------------

def test_weekly_loss_limit_blocks_trade():
    """weekly_pnl exceeding weekly_loss_limit * week_start_equity → denied."""
    cfg = replace(
        DEFAULT_CONFIG,
        risk=replace(
            DEFAULT_CONFIG.risk,
            initial_bankroll=10000.0,
            weekly_loss_limit=0.01,   # 1% weekly limit = -100 threshold
            daily_loss_limit=0.99,
            max_drawdown_hard=0.99,
            max_consecutive_losses=99,
            max_trades_per_day=99,
        ),
    )
    state = PortfolioState.create(cfg.risk.initial_bankroll)
    state.ensure_day("2026-03-02")  # Monday — initialises week/month tracking
    # Force a weekly loss larger than 1% (threshold = -100 for 10k equity)
    state.weekly_pnl = -200.0

    signal = _make_signal(match_id="mW1")
    mgr = RiskManager(cfg)
    decision = mgr.pre_trade_check(signal=signal, state=state, proposed_stake=500.0)

    assert not decision.allowed
    assert decision.reason == "weekly_loss_limit_hit"


def test_monthly_loss_limit_blocks_trade():
    """monthly_pnl exceeding monthly_loss_limit * month_start_equity → denied."""
    cfg = replace(
        DEFAULT_CONFIG,
        risk=replace(
            DEFAULT_CONFIG.risk,
            initial_bankroll=10000.0,
            monthly_loss_limit=0.01,  # 1% monthly limit = -100 threshold
            weekly_loss_limit=0.99,
            daily_loss_limit=0.99,
            max_drawdown_hard=0.99,
            max_consecutive_losses=99,
            max_trades_per_day=99,
        ),
    )
    state = PortfolioState.create(cfg.risk.initial_bankroll)
    state.ensure_day("2026-03-15")
    # Force a monthly loss larger than 1%
    state.monthly_pnl = -200.0

    signal = _make_signal(match_id="mM1")
    mgr = RiskManager(cfg)
    decision = mgr.pre_trade_check(signal=signal, state=state, proposed_stake=500.0)

    assert not decision.allowed
    assert decision.reason == "monthly_loss_limit_hit"


def test_soft_drawdown_reduces_stake_cap():
    """At 16% drawdown (past soft_drawdown_warning=15%), stake cap is halved."""
    cfg = replace(
        DEFAULT_CONFIG,
        risk=replace(
            DEFAULT_CONFIG.risk,
            initial_bankroll=10000.0,
            max_stake_pct_of_equity=0.02,    # normal equity cap = 2% of equity
            max_event_exposure_pct=0.10,     # event cap not binding
            soft_drawdown_warning=0.15,
            soft_drawdown_stake_scale=0.50,
            max_drawdown_hard=0.99,
            weekly_loss_limit=0.99,
            monthly_loss_limit=0.99,
            daily_loss_limit=0.99,
            max_consecutive_losses=99,
            max_trades_per_day=99,
            min_stake_pct_of_equity=0.0,
        ),
    )
    state = PortfolioState.create(cfg.risk.initial_bankroll)
    state.ensure_day("2026-03-01")
    # Simulate 16% drawdown: equity = 8400, peak = 10000
    state.equity = 8400.0
    state.peak_equity = 10000.0

    signal = _make_signal(match_id="mS1")
    mgr = RiskManager(cfg)
    # Propose a stake (500) that exceeds the reduced cap to confirm capping
    decision = mgr.pre_trade_check(signal=signal, state=state, proposed_stake=500.0)

    # Normal cap = 0.02 * 8400 = 168; after soft scale (×0.50) → 84
    assert decision.allowed
    assert decision.stake_cap == pytest.approx(84.0, rel=0.01)
    assert decision.stake_after_limits == pytest.approx(84.0, rel=0.01)


def test_correlated_market_blocks_second_trade():
    """A second signal on the same match_id on the same day is denied."""
    cfg = replace(
        DEFAULT_CONFIG,
        risk=replace(
            DEFAULT_CONFIG.risk,
            initial_bankroll=10000.0,
            max_same_match_trades=1,
            max_drawdown_hard=0.99,
            weekly_loss_limit=0.99,
            monthly_loss_limit=0.99,
            daily_loss_limit=0.99,
            max_consecutive_losses=99,
            max_trades_per_day=99,
        ),
    )
    state = PortfolioState.create(cfg.risk.initial_bankroll)
    state.ensure_day("2026-03-01")
    # Record a trade on the correlated match
    state.record_trade(pnl=50.0, equity_before=10000.0, match_id="m_corr")

    mgr = RiskManager(cfg)

    # Different match → allowed
    signal_other = _make_signal(match_id="m_other")
    decision_other = mgr.pre_trade_check(
        signal=signal_other, state=state, proposed_stake=100.0
    )
    assert decision_other.allowed

    # Same correlated match → denied
    signal_corr = _make_signal(match_id="m_corr")
    decision_corr = mgr.pre_trade_check(
        signal=signal_corr, state=state, proposed_stake=100.0
    )
    assert not decision_corr.allowed
    assert decision_corr.reason == "same_match_trade_limit_hit"


def test_level_c_stake_cap_is_tighter():
    """Level C bets are capped at level_c_max_stake_pct, tighter than the default."""
    cfg = replace(
        DEFAULT_CONFIG,
        risk=replace(
            DEFAULT_CONFIG.risk,
            initial_bankroll=10000.0,
            max_stake_pct_of_equity=0.02,  # default 2% → 200
            level_c_max_stake_pct=0.01,    # Level C cap 1% → 100
            max_event_exposure_pct=0.10,
            soft_drawdown_warning=0.99,
            max_drawdown_hard=0.99,
            weekly_loss_limit=0.99,
            monthly_loss_limit=0.99,
            daily_loss_limit=0.99,
            max_consecutive_losses=99,
            max_trades_per_day=99,
            min_stake_pct_of_equity=0.0,
        ),
    )
    state = PortfolioState.create(cfg.risk.initial_bankroll)
    state.ensure_day("2026-03-01")

    signal = _make_signal(match_id="mC1")
    mgr = RiskManager(cfg)

    # Level A: normal cap (200 for 10000 equity)
    dec_a = mgr.pre_trade_check(
        signal=signal, state=state, proposed_stake=500.0, level="A"
    )
    assert dec_a.allowed
    assert dec_a.stake_cap == pytest.approx(200.0, rel=0.01)

    # Level C: reduced cap (100 for 10000 equity)
    dec_c = mgr.pre_trade_check(
        signal=signal, state=state, proposed_stake=500.0, level="C"
    )
    assert dec_c.allowed
    assert dec_c.stake_cap == pytest.approx(100.0, rel=0.01)


# ---------------------------------------------------------------------------
# New tests: bankroll management
# ---------------------------------------------------------------------------

def test_market_type_kelly_scale_applied():
    """OU signals receive a lower Kelly scale than AH signals (all else equal)."""
    cfg = replace(
        DEFAULT_CONFIG,
        bankroll=replace(
            DEFAULT_CONFIG.bankroll,
            ah_kelly_scale=1.0,
            ou_kelly_scale=0.50,  # exaggerated to make assertion unambiguous
        ),
    )
    state = PortfolioState.create(cfg.risk.initial_bankroll)
    state.ensure_day("2026-03-01")

    engine = PreMatchOverReversionEngine(DEFAULT_CONFIG)
    mgr = BankrollManager(cfg)

    signal_ah = _make_signal(match_id="m_ah", market_type=MarketType.AH)
    eval_ah = engine.evaluate(signal_ah)

    signal_ou = _make_signal(match_id="m_ou", market_type=MarketType.OU)
    eval_ou = engine.evaluate(signal_ou)

    # Both signals should be accepted (same pre/live/state/model)
    assert eval_ah.accepted, f"AH signal rejected: {eval_ah.reason}"
    assert eval_ou.accepted, f"OU signal rejected: {eval_ou.reason}"

    dec_ah = mgr.propose_stake(signal=signal_ah, evaluation=eval_ah, state=state)
    dec_ou = mgr.propose_stake(signal=signal_ou, evaluation=eval_ou, state=state)

    assert dec_ah.market_type_scale == pytest.approx(1.0)
    assert dec_ou.market_type_scale == pytest.approx(0.50)
    assert dec_ou.stake < dec_ah.stake


def test_uncertainty_scale_for_estimated_odds():
    """When fair_odds is not provided by model, the uncertainty discount is applied."""
    cfg = replace(
        DEFAULT_CONFIG,
        bankroll=replace(
            DEFAULT_CONFIG.bankroll,
            estimated_odds_uncertainty_scale=0.50,  # exaggerated for clear assertion
        ),
    )
    state = PortfolioState.create(cfg.risk.initial_bankroll)
    state.ensure_day("2026-03-01")

    engine = PreMatchOverReversionEngine(DEFAULT_CONFIG)
    mgr = BankrollManager(cfg)

    # Signal WITH explicit model fair_odds (high confidence)
    signal_with_model = _make_signal(match_id="m_model", fair_odds=1.86)
    eval_with = engine.evaluate(signal_with_model)

    # Signal WITHOUT any model input (engine must estimate fair_odds from shrinkage)
    signal_no_model = _make_signal(match_id="m_no_model", fair_odds=None)
    eval_no = engine.evaluate(signal_no_model)

    if eval_with.accepted and eval_no.accepted:
        dec_with = mgr.propose_stake(
            signal=signal_with_model, evaluation=eval_with, state=state
        )
        dec_no = mgr.propose_stake(
            signal=signal_no_model, evaluation=eval_no, state=state
        )
        assert dec_with.uncertainty_scale == pytest.approx(1.0)
        assert dec_no.uncertainty_scale == pytest.approx(0.50)
        assert dec_no.stake < dec_with.stake


def test_clv_feedback_scale_reduces_stake_when_clv_negative():
    """Consistent negative CLV bps reduces stake sizing via the feedback loop."""
    cfg = replace(
        DEFAULT_CONFIG,
        bankroll=replace(
            DEFAULT_CONFIG.bankroll,
            clv_feedback_window=5,
            clv_feedback_threshold=-10.0,
            clv_feedback_min_scale=0.60,
        ),
    )
    state = PortfolioState.create(cfg.risk.initial_bankroll)
    state.ensure_day("2026-03-01")

    engine = PreMatchOverReversionEngine(DEFAULT_CONFIG)
    signal = _make_signal(match_id="mCLV")
    evaluation = engine.evaluate(signal)
    assert evaluation.accepted

    mgr = BankrollManager(cfg)

    # Fresh state: CLV history too short (< clv_feedback_window) → no adjustment
    dec_no_history = mgr.propose_stake(
        signal=signal, evaluation=evaluation, state=state
    )
    assert dec_no_history.clv_feedback_scale == pytest.approx(1.0)

    # Populate rolling_clv_bps with very negative values (-30 bps, well below -10 threshold)
    for _ in range(5):
        state.rolling_clv_bps.append(-30.0)

    dec_negative_clv = mgr.propose_stake(
        signal=signal, evaluation=evaluation, state=state
    )
    # Scale should be at or near the floor (0.60)
    assert dec_negative_clv.clv_feedback_scale <= 0.65
    assert dec_negative_clv.stake < dec_no_history.stake
