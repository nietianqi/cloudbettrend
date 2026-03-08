from __future__ import annotations

from pathlib import Path

from cloudbettrend.line_moves import (
    SnapshotStore,
    collect_competition_snapshot,
    detect_line_moves,
    detect_over_reversion_signals,
    extract_line_value,
)


class _FakeClient:
    def __init__(self, payloads: list[dict]):
        self._payloads = payloads
        self._index = 0

    def get_competition_odds(self, competition_key: str, markets: tuple[str, ...]) -> dict:
        payload = self._payloads[self._index]
        self._index += 1
        return payload


def _payload(home_line: float, home_price: float) -> dict:
    return {
        "events": [
            {
                "id": 1001,
                "name": "Alpha vs Beta",
                "cutoffTime": "2026-03-20T12:00:00Z",
                "status": "TRADING",
                "markets": {
                    "soccer.asian_handicap": {
                        "submarkets": {
                            f"handicap={home_line}": {
                                "selections": {
                                    "home": {
                                        "params": f"handicap={home_line}",
                                        "price": str(home_price),
                                        "status": "TRADING",
                                    }
                                }
                            },
                            "handicap=-0.5": {
                                "selections": {
                                    "home": {
                                        "params": "handicap=-0.5",
                                        "price": "1.70",
                                        "status": "TRADING",
                                    }
                                }
                            },
                        }
                    },
                    "soccer.total_goals": {
                        "submarkets": {
                            "total=2.5": {
                                "selections": {
                                    "over": {
                                        "params": "total=2.5",
                                        "price": "1.95",
                                        "status": "TRADING",
                                    }
                                }
                            }
                        }
                    },
                },
            }
        ]
    }


def test_extract_line_value_supports_handicap_and_total():
    assert extract_line_value("handicap=-0.75") == -0.75
    assert extract_line_value("total=2.5") == 2.5
    assert extract_line_value("foo=bar") is None


def test_detect_two_tick_ah_move(tmp_path: Path):
    db = tmp_path / "lines.db"
    store = SnapshotStore(db)
    client = _FakeClient(
        payloads=[
            _payload(home_line=-0.25, home_price=1.96),
            _payload(home_line=-0.75, home_price=1.99),
        ]
    )

    collect_competition_snapshot(
        client=client,
        store=store,
        competition_key="soccer-test-league",
        snapshot_time="2026-03-20T08:00:00+00:00",
    )
    collect_competition_snapshot(
        client=client,
        store=store,
        competition_key="soccer-test-league",
        snapshot_time="2026-03-20T11:30:00+00:00",
    )

    candidates = detect_line_moves(store=store, lookback_hours=100000, min_ticks=2.0)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.market_key == "soccer.asian_handicap"
    assert candidate.open_line == -0.25
    assert candidate.close_line == -0.75
    assert candidate.ticks_moved >= 2.0
    assert candidate.interpretation == "home_strength_up"


def test_detect_ou_pre_up_live_revert_signal(tmp_path: Path):
    db = tmp_path / "signals.db"
    store = SnapshotStore(db)

    payload_open = {
        "events": [
            {
                "id": 2002,
                "name": "Gamma vs Delta",
                "cutoffTime": "2026-03-20T12:00:00Z",
                "status": "TRADING",
                "markets": {
                    "soccer.total_goals": {
                        "submarkets": {
                            "period=ft": {
                                "selections": [
                                    {
                                        "outcome": "over",
                                        "params": "total=2.5",
                                        "price": 1.95,
                                        "status": "SELECTION_ENABLED",
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        ]
    }
    payload_close = {
        "events": [
            {
                "id": 2002,
                "name": "Gamma vs Delta",
                "cutoffTime": "2026-03-20T12:00:00Z",
                "status": "TRADING",
                "markets": {
                    "soccer.total_goals": {
                        "submarkets": {
                            "period=ft": {
                                "selections": [
                                    {
                                        "outcome": "over",
                                        "params": "total=3.0",
                                        "price": 1.93,
                                        "status": "SELECTION_ENABLED",
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        ]
    }
    payload_live = {
        "events": [
            {
                "id": 2002,
                "name": "Gamma vs Delta",
                "cutoffTime": "2026-03-20T12:00:00Z",
                "status": "TRADING",
                "markets": {
                    "soccer.total_goals": {
                        "submarkets": {
                            "period=ft": {
                                "selections": [
                                    {
                                        "outcome": "over",
                                        "params": "total=2.5",
                                        "price": 2.02,
                                        "status": "SELECTION_ENABLED",
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        ]
    }
    client = _FakeClient(payloads=[payload_open, payload_close, payload_live])

    collect_competition_snapshot(
        client=client,
        store=store,
        competition_key="soccer-test-over",
        snapshot_time="2026-03-20T10:00:00+00:00",
    )
    collect_competition_snapshot(
        client=client,
        store=store,
        competition_key="soccer-test-over",
        snapshot_time="2026-03-20T11:30:00+00:00",
    )
    collect_competition_snapshot(
        client=client,
        store=store,
        competition_key="soccer-test-over",
        snapshot_time="2026-03-20T12:05:00+00:00",
    )

    signals = detect_over_reversion_signals(
        store=store,
        lookback_hours=100000,
        min_pre_move_ticks=2.0,
        min_reversion_ticks=1.0,
        max_live_minutes=25,
    )
    assert len(signals) == 1
    sig = signals[0]
    assert sig.market_key == "soccer.total_goals"
    assert sig.open_line == 2.5
    assert sig.close_line == 3.0
    assert sig.live_line == 2.5
    assert sig.bet_side == "over"

