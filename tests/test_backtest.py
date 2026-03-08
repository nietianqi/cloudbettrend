from pathlib import Path

from cloudbettrend.backtest import BacktestRunner
from cloudbettrend.config import DEFAULT_CONFIG


def test_backtest_runner_outputs_expected_counts(tmp_path: Path):
    sample = tmp_path / "samples.jsonl"
    sample.write_text(
        '{"direction": -1, "favorite_side": "home", "pre": {"match_id": "m100", "league": "EPL", "kickoff_time": "2026-03-01T15:00:00Z", "home_team": "A", "away_team": "B", "market_type": "AH", "open_line": -0.25, "open_odds": 1.98, "close_line": -0.75, "close_odds": 1.88, "consensus_strength": 0.82, "close_price_quality": "good"}, "live": {"signal_time": "2026-03-01T15:07:30Z", "minute": 7, "second": 30, "score_home": 0, "score_away": 0, "live_line": -0.25, "live_back_odds": 1.97, "market_status": "OPEN", "seconds_since_reopen": 40, "line_jump_count_last_60s": 1, "odds_jump_count_last_60s": 1, "max_stake": 1500}, "state": {"red_home": 0, "red_away": 0, "shots_home": 2, "shots_away": 1, "shots_on_target_home": 1, "shots_on_target_away": 0, "dangerous_attacks_home": 14, "dangerous_attacks_away": 10, "corners_home": 1, "corners_away": 0}, "model": {"fair_odds": 1.86, "cost_bps": 20.0}}\n',
        encoding="utf-8",
    )

    out = tmp_path / "result.csv"
    report = BacktestRunner(DEFAULT_CONFIG).run(sample, out)

    assert report.total_events == 1
    assert report.accepted_signals == 1
    assert report.executed_trades == 1
    assert report.blocked_by_risk == 0
    # No result data in the sample → pnl=0.0 (Fix A2: unknown outcomes no longer
    # return artificial stake*expected_roi; bankroll is unchanged after unresolved trade)
    assert report.ending_bankroll == DEFAULT_CONFIG.risk.initial_bankroll
    assert report.total_pnl == 0.0
    assert out.exists()
