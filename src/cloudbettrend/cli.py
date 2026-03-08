from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import BacktestRunner
from .config import load_engine_config


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


if __name__ == "__main__":
    main()
