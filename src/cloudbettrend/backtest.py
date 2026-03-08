from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .bankroll import BankrollDecision, BankrollManager
from .config import EngineConfig
from .models import (
    ExecutionSnapshot,
    LiveMarketSnapshot,
    MarketType,
    MatchStateSnapshot,
    ModelSnapshot,
    PreMatchSnapshot,
    ResultSnapshot,
    SignalInput,
)
from .risk import PortfolioState, RiskDecision, RiskManager
from .scoring import PreMatchOverReversionEngine


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _market_type(value: str | None) -> MarketType:
    if not value:
        return MarketType.AH
    normalized = value.upper()
    if normalized == "1X2":
        return MarketType.ONE_X_TWO
    return MarketType(normalized)


def _load_rows(path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                yield item
        else:
            raise ValueError("JSON input must be an array of objects.")
        return

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        yield from reader


def _build_signal(row: dict[str, Any]) -> SignalInput:
    pre = row.get("pre", {})
    live = row.get("live", {})
    state = row.get("state", {})
    model = row.get("model", {})
    execution = row.get("execution", {})
    result = row.get("result", {})

    pre_snapshot = PreMatchSnapshot(
        match_id=str(pre.get("match_id", row.get("match_id", ""))),
        league=str(pre.get("league", row.get("league", ""))),
        kickoff_time=str(pre.get("kickoff_time", row.get("kickoff_time", ""))),
        home_team=str(pre.get("home_team", row.get("home_team", ""))),
        away_team=str(pre.get("away_team", row.get("away_team", ""))),
        market_type=_market_type(pre.get("market_type", row.get("market_type"))),
        open_line=_to_float(pre.get("open_line", row.get("open_line"))),
        open_odds=_to_float(pre.get("open_odds", row.get("open_odds")), default=1.90),
        close_line=_to_float(pre.get("close_line", row.get("close_line"))),
        close_odds=_to_float(
            pre.get("close_odds", row.get("close_odds")), default=1.90
        ),
        line_move_ticks=(
            _to_int(pre["line_move_ticks"])
            if pre.get("line_move_ticks") is not None
            else None
        ),
        odds_move_bps=(
            _to_float(pre["odds_move_bps"])
            if pre.get("odds_move_bps") is not None
            else None
        ),
        consensus_strength=_to_float(
            pre.get("consensus_strength", row.get("consensus_strength")),
            default=0.0,
        ),
        close_snapshot_time=pre.get(
            "close_snapshot_time", row.get("close_snapshot_time")
        ),
        close_price_quality=str(
            pre.get("close_price_quality", row.get("close_price_quality", "unknown"))
        ),
    )

    live_snapshot = LiveMarketSnapshot(
        signal_time=str(live.get("signal_time", row.get("signal_time", ""))),
        minute=_to_int(live.get("minute", row.get("minute")), default=0),
        second=_to_int(live.get("second", row.get("second")), default=0),
        score_home=_to_int(live.get("score_home", row.get("score_home")), default=0),
        score_away=_to_int(live.get("score_away", row.get("score_away")), default=0),
        live_line=_to_float(live.get("live_line", row.get("live_line"))),
        live_back_odds=_to_float(
            live.get("live_back_odds", row.get("live_back_odds")), default=1.90
        ),
        live_lay_odds=(
            _to_float(live["live_lay_odds"])
            if live.get("live_lay_odds") is not None
            else None
        ),
        live_spread=(
            _to_float(live["live_spread"])
            if live.get("live_spread") is not None
            else None
        ),
        max_stake=(
            _to_float(live["max_stake"])
            if live.get("max_stake") is not None
            else None
        ),
        market_status=str(live.get("market_status", row.get("market_status", "OPEN"))),
        seconds_since_reopen=(
            _to_int(live["seconds_since_reopen"])
            if live.get("seconds_since_reopen") is not None
            else None
        ),
        line_jump_count_last_60s=_to_int(
            live.get("line_jump_count_last_60s", row.get("line_jump_count_last_60s")),
            default=0,
        ),
        odds_jump_count_last_60s=_to_int(
            live.get("odds_jump_count_last_60s", row.get("odds_jump_count_last_60s")),
            default=0,
        ),
    )

    state_snapshot = MatchStateSnapshot(
        red_home=_to_int(state.get("red_home", row.get("red_home")), default=0),
        red_away=_to_int(state.get("red_away", row.get("red_away")), default=0),
        yellow_home=_to_int(state.get("yellow_home", row.get("yellow_home")), default=0),
        yellow_away=_to_int(state.get("yellow_away", row.get("yellow_away")), default=0),
        shots_home=_to_int(state.get("shots_home", row.get("shots_home")), default=0),
        shots_away=_to_int(state.get("shots_away", row.get("shots_away")), default=0),
        shots_on_target_home=_to_int(
            state.get("shots_on_target_home", row.get("shots_on_target_home")), default=0
        ),
        shots_on_target_away=_to_int(
            state.get("shots_on_target_away", row.get("shots_on_target_away")), default=0
        ),
        dangerous_attacks_home=_to_int(
            state.get("dangerous_attacks_home", row.get("dangerous_attacks_home")),
            default=0,
        ),
        dangerous_attacks_away=_to_int(
            state.get("dangerous_attacks_away", row.get("dangerous_attacks_away")),
            default=0,
        ),
        corners_home=_to_int(state.get("corners_home", row.get("corners_home")), default=0),
        corners_away=_to_int(state.get("corners_away", row.get("corners_away")), default=0),
        possession_home=(
            _to_float(state["possession_home"])
            if state.get("possession_home") is not None
            else None
        ),
        possession_away=(
            _to_float(state["possession_away"])
            if state.get("possession_away") is not None
            else None
        ),
        attacks_home=(
            _to_int(state["attacks_home"])
            if state.get("attacks_home") is not None
            else None
        ),
        attacks_away=(
            _to_int(state["attacks_away"])
            if state.get("attacks_away") is not None
            else None
        ),
        injury_flag_home=_to_bool(
            state.get("injury_flag_home", row.get("injury_flag_home")), default=False
        ),
        injury_flag_away=_to_bool(
            state.get("injury_flag_away", row.get("injury_flag_away")), default=False
        ),
        favorite_under_heavy_pressure=_to_bool(
            state.get(
                "favorite_under_heavy_pressure",
                row.get("favorite_under_heavy_pressure"),
            ),
            default=False,
        ),
        is_post_suspend_noise=_to_bool(
            state.get("is_post_suspend_noise", row.get("is_post_suspend_noise")),
            default=False,
        ),
        hard_negative_event=_to_bool(
            state.get("hard_negative_event", row.get("hard_negative_event")),
            default=False,
        ),
        market_trending_against_signal=_to_bool(
            state.get(
                "market_trending_against_signal",
                row.get("market_trending_against_signal"),
            ),
            default=False,
        ),
        reversion_explained_by_time_decay_only=_to_bool(
            state.get(
                "reversion_explained_by_time_decay_only",
                row.get("reversion_explained_by_time_decay_only"),
            ),
            default=False,
        ),
    )

    model_snapshot = ModelSnapshot(
        fair_prob=(
            _to_float(model["fair_prob"])
            if model.get("fair_prob") is not None
            else None
        ),
        fair_odds=(
            _to_float(model["fair_odds"])
            if model.get("fair_odds") is not None
            else None
        ),
        market_prob=(
            _to_float(model["market_prob"])
            if model.get("market_prob") is not None
            else None
        ),
        edge_raw=(
            _to_float(model["edge_raw"])
            if model.get("edge_raw") is not None
            else None
        ),
        edge_after_cost=(
            _to_float(model["edge_after_cost"])
            if model.get("edge_after_cost") is not None
            else None
        ),
        cost_bps=(
            _to_float(model["cost_bps"])
            if model.get("cost_bps") is not None
            else None
        ),
    )

    # FIX A7: Parse ExecutionSnapshot (previously silently ignored)
    execution_snapshot = ExecutionSnapshot(
        intended_stake=(
            _to_float(execution["intended_stake"])
            if execution.get("intended_stake") is not None
            else None
        ),
        allowed_stake=(
            _to_float(execution["allowed_stake"])
            if execution.get("allowed_stake") is not None
            else None
        ),
        placed_odds=(
            _to_float(execution["placed_odds"])
            if execution.get("placed_odds") is not None
            else None
        ),
        matched_odds=(
            _to_float(execution["matched_odds"])
            if execution.get("matched_odds") is not None
            else None
        ),
        rejected_flag=_to_bool(
            execution.get("rejected_flag"), default=False
        ),
        slippage_bps=(
            _to_float(execution["slippage_bps"])
            if execution.get("slippage_bps") is not None
            else None
        ),
        execution_delay_ms=(
            _to_int(execution["execution_delay_ms"])
            if execution.get("execution_delay_ms") is not None
            else None
        ),
    )

    result_snapshot = ResultSnapshot(
        final_score_home=(
            _to_int(result["final_score_home"])
            if result.get("final_score_home") is not None
            else None
        ),
        final_score_away=(
            _to_int(result["final_score_away"])
            if result.get("final_score_away") is not None
            else None
        ),
        outcome_winlosepush=(
            str(result["outcome_winlosepush"])
            if result.get("outcome_winlosepush") is not None
            else None
        ),
        pnl=(
            _to_float(result["pnl"])
            if result.get("pnl") is not None
            else None
        ),
        closing_line_after_1m=(
            _to_float(result["closing_line_after_1m"])
            if result.get("closing_line_after_1m") is not None
            else None
        ),
        closing_line_after_3m=(
            _to_float(result["closing_line_after_3m"])
            if result.get("closing_line_after_3m") is not None
            else None
        ),
        closing_odds_after_1m=(
            _to_float(result["closing_odds_after_1m"])
            if result.get("closing_odds_after_1m") is not None
            else None
        ),
        closing_odds_after_3m=(
            _to_float(result["closing_odds_after_3m"])
            if result.get("closing_odds_after_3m") is not None
            else None
        ),
        clv_bps=(
            _to_float(result["clv_bps"])
            if result.get("clv_bps") is not None
            else None
        ),
    )

    return SignalInput(
        pre=pre_snapshot,
        live=live_snapshot,
        state=state_snapshot,
        model=model_snapshot,
        execution=execution_snapshot,
        result=result_snapshot,
        favorite_side=str(row.get("favorite_side", "home")),
        direction=_to_int(row.get("direction"), default=1),
    )


def _compute_clv_bps(live_odds: float, close_odds: float | None) -> float | None:
    if close_odds is None or close_odds <= 1.0 or live_odds <= 1.0:
        return None
    return ((1.0 / close_odds) - (1.0 / live_odds)) * 10000.0


def _extract_day_key(value: str) -> str:
    if not value:
        return "UNKNOWN"
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else "UNKNOWN"


def _resolve_trade_pnl(signal: SignalInput, stake: float) -> float:
    """
    Resolve PnL for a trade.

    Priority:
    1. Explicit pnl from result snapshot.
    2. Outcome string (win/loss/push/void).
    3. Unknown: return 0.0 — avoids inflating backtest PnL with assumed edge.
    """
    outcome = (signal.result.outcome_winlosepush or "").strip().lower()
    if signal.result.pnl is not None:
        return signal.result.pnl
    if outcome in {"win", "won"}:
        return stake * (signal.live.live_back_odds - 1.0)
    if outcome in {"loss", "lose", "lost"}:
        return -stake
    if outcome in {"push", "void"}:
        return 0.0
    # FIX A2: return 0.0 for unknown outcomes instead of stake * expected_roi
    return 0.0


@dataclass(frozen=True)
class BacktestReport:
    total_events: int
    accepted_signals: int
    executed_trades: int
    blocked_by_risk: int
    acceptance_rate: float
    avg_signal_score: float
    avg_edge_after_cost: float
    avg_stake: float
    avg_clv_bps: float | None
    total_pnl: float
    ending_bankroll: float
    max_drawdown: float
    level_breakdown: dict[str, int]
    rows: list[dict[str, Any]]


class BacktestRunner:
    def __init__(self, config: EngineConfig):
        self.config = config
        self.engine = PreMatchOverReversionEngine(config=config)
        self.risk_manager = RiskManager(config=config)
        self.bankroll_manager = BankrollManager(config=config)
        self.state = PortfolioState.create(config.risk.initial_bankroll)

    def run(
        self, input_path: str | Path, output_path: str | Path | None = None
    ) -> BacktestReport:
        self.state = PortfolioState.create(self.config.risk.initial_bankroll)
        rows = list(_load_rows(Path(input_path)))
        outputs: list[dict[str, Any]] = []
        level_breakdown: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}

        for raw in rows:
            signal = _build_signal(raw)
            self.state.ensure_day(_extract_day_key(signal.live.signal_time))
            bankroll_before = self.state.equity
            evaluation = self.engine.evaluate(signal)
            level_breakdown[evaluation.level] = (
                level_breakdown.get(evaluation.level, 0) + 1
            )

            bankroll_decision = BankrollDecision.empty("signal_not_accepted")
            risk_decision = RiskDecision.denied("signal_not_accepted")
            is_executed = False
            matched_stake = 0.0
            realized_pnl = 0.0
            trade_return = 0.0

            # Compute CLV early so it can be passed to record_trade for feedback loop
            clv_bps = signal.result.clv_bps
            if clv_bps is None:
                clv_bps = _compute_clv_bps(
                    live_odds=signal.live.live_back_odds,
                    close_odds=signal.result.closing_odds_after_1m,
                )

            if evaluation.accepted:
                bankroll_decision = self.bankroll_manager.propose_stake(
                    signal=signal,
                    evaluation=evaluation,
                    state=self.state,
                )
                risk_decision = self.risk_manager.pre_trade_check(
                    signal=signal,
                    state=self.state,
                    proposed_stake=bankroll_decision.stake,
                    level=evaluation.level,  # level-specific stake cap
                )
                if risk_decision.allowed:
                    matched_stake = risk_decision.stake_after_limits
                    realized_pnl = _resolve_trade_pnl(
                        signal=signal,
                        stake=matched_stake,
                    )
                    trade_return = (
                        (realized_pnl / matched_stake) if matched_stake > 1e-9 else 0.0
                    )
                    self.state.record_trade(
                        pnl=realized_pnl,
                        equity_before=bankroll_before,
                        match_id=signal.pre.match_id,
                        clv_bps=clv_bps,
                    )
                    is_executed = True
                else:
                    self.state.record_blocked()

            outputs.append(
                {
                    "match_id": signal.pre.match_id,
                    "market_type": signal.pre.market_type.value,
                    "minute": signal.live.minute,
                    "signal_label": evaluation.signal_label,
                    "accepted": evaluation.accepted,
                    "reason": evaluation.reason,
                    "level": evaluation.level,
                    "signal_score": evaluation.signal_score,
                    "pre_signal_score": evaluation.pre_signal_score,
                    "reversion_score": evaluation.reversion_score,
                    "state_score": evaluation.state_score,
                    "penalty_score": evaluation.penalty_score,
                    "line_move_ticks": evaluation.line_move_ticks,
                    "reversion_ticks": evaluation.reversion_ticks,
                    "fair_odds": evaluation.fair_odds,
                    "live_back_odds": signal.live.live_back_odds,
                    "edge_raw": evaluation.edge_raw,
                    "edge_after_cost": evaluation.edge_after_cost,
                    "proposed_stake": bankroll_decision.stake,
                    "bankroll_reason": bankroll_decision.reason,
                    "matched_stake": matched_stake,
                    "stake_fraction": bankroll_decision.stake_fraction,
                    "full_kelly_fraction": bankroll_decision.full_kelly_fraction,
                    "volatility_scale": bankroll_decision.volatility_scale,
                    "drawdown_scale": bankroll_decision.drawdown_scale,
                    "level_scale": bankroll_decision.level_scale,
                    "streak_scale": bankroll_decision.streak_scale,
                    "market_type_scale": bankroll_decision.market_type_scale,
                    "uncertainty_scale": bankroll_decision.uncertainty_scale,
                    "clv_feedback_scale": bankroll_decision.clv_feedback_scale,
                    "risk_allowed": risk_decision.allowed,
                    "risk_reason": risk_decision.reason,
                    "risk_stake_cap": risk_decision.stake_cap,
                    "executed": is_executed,
                    "realized_pnl": realized_pnl,
                    "trade_return": trade_return,
                    "bankroll_before": bankroll_before,
                    "bankroll_after": self.state.equity,
                    "drawdown_ratio": self.state.drawdown_ratio,
                    "weekly_pnl": self.state.weekly_pnl,
                    "monthly_pnl": self.state.monthly_pnl,
                    "clv_bps": clv_bps,
                }
            )

        accepted_rows = [r for r in outputs if r["accepted"]]
        executed_rows = [r for r in outputs if r["executed"]]
        blocked_rows = [r for r in outputs if r["accepted"] and not r["risk_allowed"]]
        avg_score = (
            sum(r["signal_score"] for r in outputs) / len(outputs) if outputs else 0.0
        )
        avg_edge = (
            sum(r["edge_after_cost"] for r in accepted_rows) / len(accepted_rows)
            if accepted_rows
            else 0.0
        )
        avg_stake = (
            sum(r["matched_stake"] for r in executed_rows) / len(executed_rows)
            if executed_rows
            else 0.0
        )
        clv_values = [r["clv_bps"] for r in accepted_rows if r["clv_bps"] is not None]
        avg_clv = (sum(clv_values) / len(clv_values)) if clv_values else None
        total_pnl = sum(r["realized_pnl"] for r in executed_rows)

        report = BacktestReport(
            total_events=len(outputs),
            accepted_signals=len(accepted_rows),
            executed_trades=len(executed_rows),
            blocked_by_risk=len(blocked_rows),
            acceptance_rate=(len(accepted_rows) / len(outputs)) if outputs else 0.0,
            avg_signal_score=avg_score,
            avg_edge_after_cost=avg_edge,
            avg_stake=avg_stake,
            avg_clv_bps=avg_clv,
            total_pnl=total_pnl,
            ending_bankroll=self.state.equity,
            max_drawdown=self.state.max_drawdown_seen,
            level_breakdown=level_breakdown,
            rows=outputs,
        )

        if output_path is not None and outputs:
            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(outputs[0].keys()))
                writer.writeheader()
                writer.writerows(outputs)

        return report
