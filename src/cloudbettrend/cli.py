from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import BacktestRunner
from .cloudbet_feed import CloudbetAPIError, CloudbetFeedClient
from .config import load_engine_config
from .line_moves import (
    DEFAULT_QUERY_MARKETS,
    SnapshotStore,
    collect_competition_snapshot,
    detect_line_moves,
    write_line_move_candidates,
)


def _split_csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _build_cloudbet_client(api_key_env: str, base_url: str) -> CloudbetFeedClient:
    return CloudbetFeedClient.from_env(env_var=api_key_env, base_url=base_url)


def _resolve_competitions(
    *,
    client: CloudbetFeedClient,
    explicit_competitions: list[str] | None,
    sport_key: str,
    max_competitions: int | None,
) -> list[str]:
    if explicit_competitions:
        return explicit_competitions

    payload = client.get_sport_competitions(sport_key=sport_key)
    competitions = payload.get("competitions", []) or []
    keys = [str(c.get("key")) for c in competitions if c.get("key")]

    # Some sport responses (e.g. soccer) return competitions nested under categories.
    if not keys:
        categories = payload.get("categories", []) or []
        for category in categories:
            for comp in (category.get("competitions", []) or []):
                key = comp.get("key")
                if key:
                    keys.append(str(key))

    if max_competitions is not None and max_competitions > 0:
        return keys[:max_competitions]
    return keys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloudbettrend",
        description="Pre-match strong signal + early in-play over-reversion research framework.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="Run backtest on JSONL/CSV samples.")
    backtest.add_argument("--input", required=True, help="Path to JSONL/CSV dataset.")
    backtest.add_argument("--config", default=None, help="Path to YAML config.")
    backtest.add_argument("--output", default=None, help="Optional CSV output path.")

    collect = subparsers.add_parser(
        "collect-cloudbet",
        help="Collect Cloudbet pre-match line snapshots into SQLite.",
    )
    collect.add_argument(
        "--db",
        default="data/cloudbet_lines.db",
        help="SQLite DB path for line snapshots.",
    )
    collect.add_argument(
        "--competition",
        action="append",
        default=[],
        help="Competition key. Use multiple --competition to pass multiple keys.",
    )
    collect.add_argument(
        "--sport",
        default="soccer",
        help="Sport key used when --competition is not provided.",
    )
    collect.add_argument(
        "--max-competitions",
        type=int,
        default=0,
        help="Limit competitions when auto-loading by sport. 0 means all.",
    )
    collect.add_argument(
        "--markets",
        default=",".join(DEFAULT_QUERY_MARKETS),
        help="Cloudbet markets query (comma separated).",
    )
    collect.add_argument(
        "--api-key-env",
        default="CLOUDBET_API_KEY",
        help="Environment variable name holding Cloudbet API key.",
    )
    collect.add_argument(
        "--base-url",
        default="https://sports-api.cloudbet.com",
        help="Cloudbet sports API base URL.",
    )

    detect = subparsers.add_parser(
        "detect-line-moves",
        help="Detect matches with pre-match line moves >= N ticks.",
    )
    detect.add_argument(
        "--db",
        default="data/cloudbet_lines.db",
        help="SQLite DB path containing snapshots.",
    )
    detect.add_argument(
        "--lookback-hours",
        type=int,
        default=48,
        help="Scan snapshots in this lookback window.",
    )
    detect.add_argument(
        "--min-ticks",
        type=float,
        default=2.0,
        help="Minimum ticks moved. 2.0 means two quarter-goal ticks.",
    )
    detect.add_argument(
        "--output",
        default=None,
        help="Optional CSV output for detected candidates.",
    )
    detect.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max rows printed to terminal.",
    )
    detect.add_argument(
        "--include-live",
        action="store_true",
        help="Include post-kickoff snapshots (default only pre-match snapshots).",
    )

    scan = subparsers.add_parser(
        "cloudbet-scan",
        help="Collect latest Cloudbet snapshot then detect >= N tick line moves.",
    )
    scan.add_argument(
        "--db",
        default="data/cloudbet_lines.db",
        help="SQLite DB path for snapshots and detection.",
    )
    scan.add_argument(
        "--competition",
        action="append",
        default=[],
        help="Competition key. Use multiple --competition to pass multiple keys.",
    )
    scan.add_argument(
        "--sport",
        default="soccer",
        help="Sport key used when --competition is not provided.",
    )
    scan.add_argument(
        "--max-competitions",
        type=int,
        default=0,
        help="Limit competitions when auto-loading by sport. 0 means all.",
    )
    scan.add_argument(
        "--markets",
        default=",".join(DEFAULT_QUERY_MARKETS),
        help="Cloudbet markets query (comma separated).",
    )
    scan.add_argument(
        "--api-key-env",
        default="CLOUDBET_API_KEY",
        help="Environment variable name holding Cloudbet API key.",
    )
    scan.add_argument(
        "--base-url",
        default="https://sports-api.cloudbet.com",
        help="Cloudbet sports API base URL.",
    )
    scan.add_argument(
        "--lookback-hours",
        type=int,
        default=48,
        help="Scan snapshots in this lookback window.",
    )
    scan.add_argument(
        "--min-ticks",
        type=float,
        default=2.0,
        help="Minimum ticks moved. 2.0 means two quarter-goal ticks.",
    )
    scan.add_argument(
        "--output",
        default=None,
        help="Optional CSV output for detected candidates.",
    )
    scan.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max rows printed to terminal.",
    )
    scan.add_argument(
        "--include-live",
        action="store_true",
        help="Include post-kickoff snapshots (default only pre-match snapshots).",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "backtest":
        config = load_engine_config(args.config)
        runner = BacktestRunner(config)
        report = runner.run(input_path=args.input, output_path=args.output)

        print(f"total_events={report.total_events}")
        print(f"accepted_signals={report.accepted_signals}")
        print(f"executed_trades={report.executed_trades}")
        print(f"blocked_by_risk={report.blocked_by_risk}")
        print(f"acceptance_rate={report.acceptance_rate:.2%}")
        print(f"avg_signal_score={report.avg_signal_score:.2f}")
        print(f"avg_edge_after_cost={report.avg_edge_after_cost:.4f}")
        print(f"avg_stake={report.avg_stake:.2f}")
        print(
            "avg_clv_bps="
            + (f"{report.avg_clv_bps:.2f}" if report.avg_clv_bps is not None else "N/A")
        )
        print(f"total_pnl={report.total_pnl:.2f}")
        print(f"ending_bankroll={report.ending_bankroll:.2f}")
        print(f"max_drawdown={report.max_drawdown:.2%}")
        print(f"level_breakdown={report.level_breakdown}")
        if args.output:
            print(f"output={Path(args.output).resolve()}")
    elif args.command == "collect-cloudbet":
        try:
            client = _build_cloudbet_client(
                api_key_env=args.api_key_env,
                base_url=args.base_url,
            )
        except CloudbetAPIError as exc:
            raise SystemExit(str(exc))

        competitions = _resolve_competitions(
            client=client,
            explicit_competitions=args.competition,
            sport_key=args.sport,
            max_competitions=(args.max_competitions if args.max_competitions > 0 else None),
        )
        if not competitions:
            raise SystemExit("No competitions to collect.")

        store = SnapshotStore(args.db)
        markets = tuple(_split_csv(args.markets))
        total_events = 0
        total_snapshots = 0
        for key in competitions:
            stats = collect_competition_snapshot(
                client=client,
                store=store,
                competition_key=key,
                markets=markets,
            )
            total_events += stats["event_count"]
            total_snapshots += stats["snapshot_count"]
            print(
                f"competition={key} events={stats['event_count']} snapshots={stats['snapshot_count']}"
            )
        print(f"db={Path(args.db).resolve()}")
        print(f"competitions={len(competitions)}")
        print(f"events={total_events}")
        print(f"snapshots={total_snapshots}")
    elif args.command == "detect-line-moves":
        store = SnapshotStore(args.db)
        candidates = detect_line_moves(
            store=store,
            lookback_hours=args.lookback_hours,
            min_ticks=args.min_ticks,
            prematch_only=not args.include_live,
        )
        if args.output:
            write_line_move_candidates(args.output, candidates)
        print(f"detected={len(candidates)}")
        for item in candidates[: args.limit]:
            print(
                f"{item.event_start_time} | {item.event_name} | {item.market_key} | "
                f"{item.open_line}->{item.close_line} | ticks={item.ticks_moved:.2f} | {item.interpretation}"
            )
        if args.output:
            print(f"output={Path(args.output).resolve()}")
    elif args.command == "cloudbet-scan":
        try:
            client = _build_cloudbet_client(
                api_key_env=args.api_key_env,
                base_url=args.base_url,
            )
        except CloudbetAPIError as exc:
            raise SystemExit(str(exc))

        competitions = _resolve_competitions(
            client=client,
            explicit_competitions=args.competition,
            sport_key=args.sport,
            max_competitions=(args.max_competitions if args.max_competitions > 0 else None),
        )
        if not competitions:
            raise SystemExit("No competitions to collect.")

        store = SnapshotStore(args.db)
        markets = tuple(_split_csv(args.markets))
        total_events = 0
        total_snapshots = 0
        for key in competitions:
            stats = collect_competition_snapshot(
                client=client,
                store=store,
                competition_key=key,
                markets=markets,
            )
            total_events += stats["event_count"]
            total_snapshots += stats["snapshot_count"]

        candidates = detect_line_moves(
            store=store,
            lookback_hours=args.lookback_hours,
            min_ticks=args.min_ticks,
            prematch_only=not args.include_live,
        )
        if args.output:
            write_line_move_candidates(args.output, candidates)

        print(f"collected_competitions={len(competitions)}")
        print(f"collected_events={total_events}")
        print(f"collected_snapshots={total_snapshots}")
        print(f"detected={len(candidates)}")
        for item in candidates[: args.limit]:
            print(
                f"{item.event_start_time} | {item.event_name} | {item.market_key} | "
                f"{item.open_line}->{item.close_line} | ticks={item.ticks_moved:.2f} | {item.interpretation}"
            )
        if args.output:
            print(f"output={Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
