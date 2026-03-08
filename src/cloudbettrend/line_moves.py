from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from .cloudbet_feed import CloudbetFeedClient


DEFAULT_QUERY_MARKETS = ("soccer.asian_handicap", "soccer.total_goals")
SUPPORTED_MARKETS = {
    "soccer.asian_handicap": {"canonical_outcome": "home", "tick_size": 0.25},
    "soccer.total_goals": {"canonical_outcome": "over", "tick_size": 0.25},
}


def _normalize_market_key(market_key: str) -> str:
    lowered = market_key.strip()
    aliases = {
        "soccer.asianHandicap": "soccer.asian_handicap",
        "soccer.asian_handicap": "soccer.asian_handicap",
        "soccer.totalGoals": "soccer.total_goals",
        "soccer.total_goals": "soccer.total_goals",
    }
    return aliases.get(lowered, lowered)


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_line_value(params_str: str | None) -> float | None:
    if not params_str:
        return None
    parsed = parse_qs(params_str, keep_blank_values=True)
    for key in ("handicap", "total", "line", "points"):
        values = parsed.get(key)
        if values:
            return _parse_float(values[0])
    return None


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_time: str
    competition_key: str
    event_id: int
    event_name: str
    event_start_time: str
    event_status: str
    market_key: str
    submarket_key: str
    outcome: str
    params: str
    line_value: float
    price: float | None
    min_stake: float | None
    max_stake: float | None
    selection_status: str


@dataclass(frozen=True)
class LineMoveCandidate:
    competition_key: str
    event_id: int
    event_name: str
    event_start_time: str
    market_key: str
    open_snapshot_time: str
    close_snapshot_time: str
    open_line: float
    close_line: float
    open_price: float | None
    close_price: float | None
    delta_line: float
    ticks_moved: float
    direction: str
    interpretation: str


@dataclass(frozen=True)
class OverReversionSignal:
    competition_key: str
    event_id: int
    event_name: str
    event_start_time: str
    market_key: str
    open_snapshot_time: str
    close_snapshot_time: str
    live_snapshot_time: str
    minutes_after_kickoff: float
    open_line: float
    close_line: float
    live_line: float
    open_price: float | None
    close_price: float | None
    live_price: float | None
    pre_move_ticks: float
    reversion_ticks: float
    bet_side: str
    signal_label: str
    note: str


class SnapshotStore:
    def __init__(self, db_path: str | Path):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS line_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_time TEXT NOT NULL,
                    competition_key TEXT NOT NULL,
                    event_id INTEGER NOT NULL,
                    event_name TEXT NOT NULL,
                    event_start_time TEXT NOT NULL,
                    event_status TEXT,
                    market_key TEXT NOT NULL,
                    submarket_key TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    params TEXT,
                    line_value REAL NOT NULL,
                    price REAL,
                    min_stake REAL,
                    max_stake REAL,
                    selection_status TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_line_snapshots_event ON line_snapshots(event_id, market_key, snapshot_time)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_line_snapshots_time ON line_snapshots(snapshot_time)"
            )

    def insert(self, records: list[SnapshotRecord]) -> None:
        if not records:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO line_snapshots (
                    snapshot_time, competition_key, event_id, event_name,
                    event_start_time, event_status, market_key, submarket_key,
                    outcome, params, line_value, price, min_stake, max_stake,
                    selection_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.snapshot_time,
                        r.competition_key,
                        r.event_id,
                        r.event_name,
                        r.event_start_time,
                        r.event_status,
                        r.market_key,
                        r.submarket_key,
                        r.outcome,
                        r.params,
                        r.line_value,
                        r.price,
                        r.min_stake,
                        r.max_stake,
                        r.selection_status,
                    )
                    for r in records
                ],
            )

    def fetch_prematch_rows(self, since_iso: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM line_snapshots
                WHERE snapshot_time >= ?
                ORDER BY event_id, market_key, snapshot_time
                """,
                (since_iso,),
            ).fetchall()
        return rows


def _event_name(event: dict[str, Any]) -> str:
    if isinstance(event.get("name"), str) and event["name"].strip():
        return event["name"].strip()

    home = ((event.get("home") or {}).get("name") or "").strip()
    away = ((event.get("away") or {}).get("name") or "").strip()
    if home and away:
        return f"{home} vs {away}"
    return str(event.get("id", "unknown_event"))


def _selection_is_active(row: sqlite3.Row) -> bool:
    status = str(row["selection_status"] or "").upper()
    price = _parse_float(row["price"]) or 0.0
    return status in {"TRADING", "SELECTION_ENABLED", "ENABLED"} and price > 0


def _line_to_ticks(line: float, tick_size: float) -> float:
    if tick_size <= 0:
        return 0.0
    return line / tick_size


def _approx_equal(left: float, right: float, tolerance_ticks: float, tick_size: float) -> bool:
    return abs(left - right) <= abs(tolerance_ticks * tick_size) + 1e-9


def collect_competition_snapshot(
    *,
    client: CloudbetFeedClient,
    store: SnapshotStore,
    competition_key: str,
    markets: tuple[str, ...] = DEFAULT_QUERY_MARKETS,
    snapshot_time: str | None = None,
) -> dict[str, int]:
    payload = client.get_competition_odds(competition_key=competition_key, markets=markets)
    events = payload.get("events", [])
    ts = snapshot_time or _iso_now_utc()
    records: list[SnapshotRecord] = []
    seen_events: set[int] = set()

    for event in events:
        event_id = int(event.get("id", 0))
        if event_id <= 0:
            continue

        seen_events.add(event_id)
        event_start_time = str(event.get("cutoffTime") or event.get("startTime") or "")
        event_status = str(event.get("status") or "")
        event_name = _event_name(event)

        markets_map = event.get("markets", {}) or {}
        for raw_market_key, market_data in markets_map.items():
            market_key = _normalize_market_key(str(raw_market_key))
            settings = SUPPORTED_MARKETS.get(market_key)
            if settings is None:
                continue

            canonical_outcome = settings["canonical_outcome"]
            submarkets = market_data.get("submarkets", {}) or {}
            for submarket_key, submarket_data in submarkets.items():
                selections_raw = submarket_data.get("selections", []) or []
                selections: list[dict[str, Any]] = []
                if isinstance(selections_raw, dict):
                    for outcome_key, selection_value in selections_raw.items():
                        if isinstance(selection_value, dict):
                            selection_copy = dict(selection_value)
                            selection_copy.setdefault("outcome", outcome_key)
                            selections.append(selection_copy)
                elif isinstance(selections_raw, list):
                    selections = [s for s in selections_raw if isinstance(s, dict)]

                for selection in selections:
                    outcome_name = str(selection.get("outcome") or "")
                    if outcome_name != canonical_outcome:
                        continue

                    params = str(
                        selection.get("params")
                        or submarket_data.get("params")
                        or submarket_key
                        or ""
                    )
                    line_value = extract_line_value(params)
                    if line_value is None:
                        continue

                    records.append(
                        SnapshotRecord(
                            snapshot_time=ts,
                            competition_key=competition_key,
                            event_id=event_id,
                            event_name=event_name,
                            event_start_time=event_start_time,
                            event_status=event_status,
                            market_key=market_key,
                            submarket_key=str(submarket_key),
                            outcome=outcome_name,
                            params=params,
                            line_value=line_value,
                            price=_parse_float(selection.get("price")),
                            min_stake=_parse_float(selection.get("minStake")),
                            max_stake=_parse_float(selection.get("maxStake")),
                            selection_status=str(selection.get("status") or ""),
                        )
                    )

    store.insert(records)
    return {
        "competition_count": 1,
        "event_count": len(seen_events),
        "snapshot_count": len(records),
    }


def _main_line_per_snapshot(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    # A market contains multiple lines at one timestamp. Use price closest to even odds
    # as the current "main line" representative.
    by_time: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_time.setdefault(str(row["snapshot_time"]), []).append(row)

    def _price_score(row: sqlite3.Row) -> float:
        price = _parse_float(row["price"])
        if price is None or price <= 0:
            return 9999.0
        # Cloudbet feeds can represent price in different conventions. Anchor around
        # 2.0 (decimal) or 1.0 (HK-like) depending on range.
        anchor = 1.0 if price <= 1.2 else 2.0
        return abs(price - anchor)

    selected: list[sqlite3.Row] = []
    for _, candidates in sorted(by_time.items(), key=lambda item: item[0]):
        active = [r for r in candidates if _selection_is_active(r)]
        pool = active or candidates
        best = min(pool, key=_price_score)
        selected.append(best)
    return selected


def detect_line_moves(
    *,
    store: SnapshotStore,
    lookback_hours: int = 48,
    min_ticks: float = 2.0,
    prematch_only: bool = True,
) -> list[LineMoveCandidate]:
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    rows = store.fetch_prematch_rows(since_iso=since.replace(microsecond=0).isoformat())

    grouped: dict[tuple[int, str], list[sqlite3.Row]] = {}
    for row in rows:
        start_dt = _parse_iso_utc(row["event_start_time"])
        snapshot_dt = _parse_iso_utc(row["snapshot_time"])
        if start_dt is None or snapshot_dt is None:
            continue
        if prematch_only and snapshot_dt > start_dt:
            continue
        grouped.setdefault((int(row["event_id"]), str(row["market_key"])), []).append(row)

    candidates: list[LineMoveCandidate] = []
    for (_, market_key), series in grouped.items():
        main_series = _main_line_per_snapshot(series)
        if len(main_series) < 2:
            continue

        open_row = main_series[0]
        close_row = main_series[-1]
        open_line = float(open_row["line_value"])
        close_line = float(close_row["line_value"])
        delta = close_line - open_line
        settings = SUPPORTED_MARKETS.get(str(market_key))
        if settings is None:
            continue
        ticks = abs(delta) / float(settings["tick_size"])
        if ticks + 1e-9 < min_ticks:
            continue

        if delta > 0:
            direction = "line_up"
        elif delta < 0:
            direction = "line_down"
        else:
            direction = "flat"

        if market_key == "soccer.asian_handicap":
            interpretation = "home_strength_down" if delta > 0 else "home_strength_up"
        elif market_key == "soccer.total_goals":
            interpretation = "goal_expectancy_up" if delta > 0 else "goal_expectancy_down"
        else:
            interpretation = "line_shift"

        candidates.append(
            LineMoveCandidate(
                competition_key=str(close_row["competition_key"]),
                event_id=int(close_row["event_id"]),
                event_name=str(close_row["event_name"]),
                event_start_time=str(close_row["event_start_time"]),
                market_key=str(market_key),
                open_snapshot_time=str(open_row["snapshot_time"]),
                close_snapshot_time=str(close_row["snapshot_time"]),
                open_line=open_line,
                close_line=close_line,
                open_price=_parse_float(open_row["price"]),
                close_price=_parse_float(close_row["price"]),
                delta_line=delta,
                ticks_moved=ticks,
                direction=direction,
                interpretation=interpretation,
            )
        )

    candidates.sort(key=lambda c: (c.ticks_moved, c.event_start_time), reverse=True)
    return candidates


def detect_over_reversion_signals(
    *,
    store: SnapshotStore,
    lookback_hours: int = 96,
    min_pre_move_ticks: float = 2.0,
    min_reversion_ticks: float = 1.0,
    max_live_minutes: int = 25,
    tolerance_ticks: float = 0.0,
) -> list[OverReversionSignal]:
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    rows = store.fetch_prematch_rows(since_iso=since.replace(microsecond=0).isoformat())

    grouped: dict[tuple[int, str], list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault((int(row["event_id"]), str(row["market_key"])), []).append(row)

    signals: list[OverReversionSignal] = []
    for (_, market_key), series in grouped.items():
        settings = SUPPORTED_MARKETS.get(market_key)
        if settings is None:
            continue
        tick_size = float(settings["tick_size"])

        timeline = _main_line_per_snapshot(series)
        if len(timeline) < 3:
            continue

        kickoff_dt = _parse_iso_utc(timeline[0]["event_start_time"])
        if kickoff_dt is None:
            continue

        pre_rows = []
        live_rows = []
        for row in timeline:
            snap_dt = _parse_iso_utc(row["snapshot_time"])
            if snap_dt is None:
                continue
            if snap_dt <= kickoff_dt:
                pre_rows.append((snap_dt, row))
            else:
                delta_min = (snap_dt - kickoff_dt).total_seconds() / 60.0
                if delta_min <= max_live_minutes:
                    live_rows.append((snap_dt, row, delta_min))

        if len(pre_rows) < 2 or not live_rows:
            continue

        open_row = pre_rows[0][1]
        close_row = pre_rows[-1][1]
        open_line = float(open_row["line_value"])
        close_line = float(close_row["line_value"])
        pre_move_ticks = abs(_line_to_ticks(close_line - open_line, tick_size))
        if pre_move_ticks + 1e-9 < min_pre_move_ticks:
            continue

        pre_delta = close_line - open_line
        if abs(pre_delta) <= 1e-9:
            continue

        triggered: OverReversionSignal | None = None
        for snap_dt, live_row, minutes_after_kickoff in live_rows:
            live_line = float(live_row["line_value"])

            bet_side = ""
            signal_label = ""
            note = ""

            if market_key == "soccer.total_goals":
                if pre_delta > 0:
                    # 2.5 -> 3.0 then live back to 2.5: bet Over
                    cond = (live_line < open_line) or _approx_equal(
                        live_line, open_line, tolerance_ticks, tick_size
                    )
                    if cond:
                        bet_side = "over"
                        signal_label = "OU_PRE_UP_LIVE_REVERT_OVER"
                        note = "pre_total_up_then_live_back_to_open_or_lower"
                else:
                    # 3.0 -> 2.5 then live back to 3.0: bet Under
                    cond = (live_line > open_line) or _approx_equal(
                        live_line, open_line, tolerance_ticks, tick_size
                    )
                    if cond:
                        bet_side = "under"
                        signal_label = "OU_PRE_DOWN_LIVE_REVERT_UNDER"
                        note = "pre_total_down_then_live_back_to_open_or_higher"
            elif market_key == "soccer.asian_handicap":
                if pre_delta < 0:
                    # home -0.75 -> -1.25 then live back to -0.75: bet home
                    cond = (live_line > open_line) or _approx_equal(
                        live_line, open_line, tolerance_ticks, tick_size
                    )
                    if cond:
                        bet_side = "home"
                        signal_label = "AH_HOME_PRE_UP_LIVE_REVERT_HOME"
                        note = "home_strength_up_pre_then_reverted_to_open"
                else:
                    # home -1.25 -> -0.75 then live back to -1.25: bet away
                    cond = (live_line < open_line) or _approx_equal(
                        live_line, open_line, tolerance_ticks, tick_size
                    )
                    if cond:
                        bet_side = "away"
                        signal_label = "AH_HOME_PRE_DOWN_LIVE_REVERT_AWAY"
                        note = "home_strength_down_pre_then_reverted_to_open"
            else:
                continue

            if not bet_side:
                continue

            reversion_ticks = abs(_line_to_ticks(live_line - close_line, tick_size))
            if reversion_ticks + 1e-9 < min_reversion_ticks:
                continue

            triggered = OverReversionSignal(
                competition_key=str(live_row["competition_key"]),
                event_id=int(live_row["event_id"]),
                event_name=str(live_row["event_name"]),
                event_start_time=str(live_row["event_start_time"]),
                market_key=market_key,
                open_snapshot_time=str(open_row["snapshot_time"]),
                close_snapshot_time=str(close_row["snapshot_time"]),
                live_snapshot_time=str(live_row["snapshot_time"]),
                minutes_after_kickoff=minutes_after_kickoff,
                open_line=open_line,
                close_line=close_line,
                live_line=live_line,
                open_price=_parse_float(open_row["price"]),
                close_price=_parse_float(close_row["price"]),
                live_price=_parse_float(live_row["price"]),
                pre_move_ticks=pre_move_ticks,
                reversion_ticks=reversion_ticks,
                bet_side=bet_side,
                signal_label=signal_label,
                note=note,
            )
            break

        if triggered is not None:
            signals.append(triggered)

    signals.sort(key=lambda s: (s.event_start_time, s.minutes_after_kickoff))
    return signals


def write_line_move_candidates(path: str | Path, candidates: list[LineMoveCandidate]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "competition_key",
            "event_id",
            "event_name",
            "event_start_time",
            "market_key",
            "open_snapshot_time",
            "close_snapshot_time",
            "open_line",
            "close_line",
            "open_price",
            "close_price",
            "delta_line",
            "ticks_moved",
            "direction",
            "interpretation",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for c in candidates:
            writer.writerow(
                {
                    "competition_key": c.competition_key,
                    "event_id": c.event_id,
                    "event_name": c.event_name,
                    "event_start_time": c.event_start_time,
                    "market_key": c.market_key,
                    "open_snapshot_time": c.open_snapshot_time,
                    "close_snapshot_time": c.close_snapshot_time,
                    "open_line": c.open_line,
                    "close_line": c.close_line,
                    "open_price": c.open_price,
                    "close_price": c.close_price,
                    "delta_line": c.delta_line,
                    "ticks_moved": c.ticks_moved,
                    "direction": c.direction,
                    "interpretation": c.interpretation,
                }
            )


def write_over_reversion_signals(
    path: str | Path, signals: list[OverReversionSignal]
) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "competition_key",
            "event_id",
            "event_name",
            "event_start_time",
            "market_key",
            "open_snapshot_time",
            "close_snapshot_time",
            "live_snapshot_time",
            "minutes_after_kickoff",
            "open_line",
            "close_line",
            "live_line",
            "open_price",
            "close_price",
            "live_price",
            "pre_move_ticks",
            "reversion_ticks",
            "bet_side",
            "signal_label",
            "note",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for s in signals:
            writer.writerow(
                {
                    "competition_key": s.competition_key,
                    "event_id": s.event_id,
                    "event_name": s.event_name,
                    "event_start_time": s.event_start_time,
                    "market_key": s.market_key,
                    "open_snapshot_time": s.open_snapshot_time,
                    "close_snapshot_time": s.close_snapshot_time,
                    "live_snapshot_time": s.live_snapshot_time,
                    "minutes_after_kickoff": s.minutes_after_kickoff,
                    "open_line": s.open_line,
                    "close_line": s.close_line,
                    "live_line": s.live_line,
                    "open_price": s.open_price,
                    "close_price": s.close_price,
                    "live_price": s.live_price,
                    "pre_move_ticks": s.pre_move_ticks,
                    "reversion_ticks": s.reversion_ticks,
                    "bet_side": s.bet_side,
                    "signal_label": s.signal_label,
                    "note": s.note,
                }
            )
