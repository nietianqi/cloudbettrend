from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from .cloudbet_feed import CloudbetFeedClient


DEFAULT_QUERY_MARKETS = ("soccer.asianHandicap", "soccer.totalGoals")
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
                selections = submarket_data.get("selections", {}) or {}
                for outcome, selection in selections.items():
                    outcome_name = str(outcome)
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

    selected: list[sqlite3.Row] = []
    for _, candidates in sorted(by_time.items(), key=lambda item: item[0]):
        best = min(
            candidates,
            key=lambda r: abs((r["price"] if r["price"] is not None else 99.0) - 2.0),
        )
        selected.append(best)
    return selected


def detect_line_moves(
    *,
    store: SnapshotStore,
    lookback_hours: int = 48,
    min_ticks: float = 2.0,
) -> list[LineMoveCandidate]:
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    rows = store.fetch_prematch_rows(since_iso=since.replace(microsecond=0).isoformat())

    grouped: dict[tuple[int, str], list[sqlite3.Row]] = {}
    for row in rows:
        start_dt = _parse_iso_utc(row["event_start_time"])
        snapshot_dt = _parse_iso_utc(row["snapshot_time"])
        if start_dt is None or snapshot_dt is None:
            continue
        if snapshot_dt > start_dt:
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
