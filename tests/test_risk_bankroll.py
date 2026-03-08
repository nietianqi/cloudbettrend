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
from cloudbettrend.risk import PortfolioState
from cloudbettrend.scoring import PreMatchOverReversionEngine


def _accepted_signal() -> SignalInput:
    return SignalInput(
        pre=PreMatchSnapshot(
            match_id="m1",
            league="EPL",
            kickoff_time="2026-03-01T15:00:00Z",
            home_team="A",
            away_team="B",
            market_type=MarketType.AH,
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
            max_stake=1500,
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
        model=ModelSnapshot(fair_odds=1.86, cost_bps=20.0),
        favorite_side="home",
        direction=-1,
    )


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
