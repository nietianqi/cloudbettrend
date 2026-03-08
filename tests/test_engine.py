from cloudbettrend.config import DEFAULT_CONFIG
from cloudbettrend.models import (
    LiveMarketSnapshot,
    MarketType,
    MatchStateSnapshot,
    ModelSnapshot,
    PreMatchSnapshot,
    SignalInput,
)
from cloudbettrend.scoring import PreMatchOverReversionEngine


def _base_ah_signal(red_home: int = 0) -> SignalInput:
    pre = PreMatchSnapshot(
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
        consensus_strength=0.80,
        close_price_quality="good",
    )
    live = LiveMarketSnapshot(
        signal_time="2026-03-01T15:08:00Z",
        minute=8,
        second=0,
        score_home=0,
        score_away=0,
        live_line=-0.25,
        live_back_odds=1.98,
        market_status="OPEN",
        seconds_since_reopen=30,
        line_jump_count_last_60s=1,
        odds_jump_count_last_60s=1,
        max_stake=1000,
    )
    state = MatchStateSnapshot(
        red_home=red_home,
        red_away=0,
        shots_home=2,
        shots_away=1,
        shots_on_target_home=1,
        shots_on_target_away=0,
        dangerous_attacks_home=13,
        dangerous_attacks_away=8,
        corners_home=1,
        corners_away=0,
    )
    model = ModelSnapshot(fair_odds=1.86, cost_bps=20.0)
    return SignalInput(
        pre=pre,
        live=live,
        state=state,
        model=model,
        favorite_side="home",
        direction=-1,
    )


def test_accepts_strong_ah_over_reversion():
    engine = PreMatchOverReversionEngine(config=DEFAULT_CONFIG)
    result = engine.evaluate(_base_ah_signal())
    assert result.accepted is True
    assert result.signal_label == "AH_OVER_REVERSION"
    assert result.reversion_ticks >= 1
    assert result.pre_signal_score >= 3
    assert result.signal_score >= 6


def test_rejects_when_red_card_present():
    engine = PreMatchOverReversionEngine(config=DEFAULT_CONFIG)
    result = engine.evaluate(_base_ah_signal(red_home=1))
    assert result.accepted is False
    assert "red_card_present" in (result.reason or "")

