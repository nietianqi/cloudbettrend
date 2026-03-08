from __future__ import annotations

from dataclasses import dataclass

from .config import EngineConfig
from .filters import HardFilter
from .models import MarketType, SignalEvaluation, SignalInput


def _line_to_ticks(value: float) -> int:
    return int(round(value * 4))


def _normalize_direction(signal: SignalInput) -> int:
    if signal.direction in (-1, 1):
        return signal.direction
    raw = _line_to_ticks(signal.pre.close_line) - _line_to_ticks(signal.pre.open_line)
    return 1 if raw >= 0 else -1


def _safe_odds(odds: float | None, fallback: float) -> float:
    if odds is None or odds <= 1.0:
        return fallback
    return odds


@dataclass
class PreMatchOverReversionEngine:
    config: EngineConfig
    hard_filter: HardFilter = HardFilter()

    def build_pre_signal_score(self, signal: SignalInput, line_move_ticks: int) -> int:
        score = 0
        cfg = self.config.pre_signal

        if line_move_ticks >= cfg.strong_move_ticks:
            score += 2
        elif line_move_ticks >= cfg.weak_move_ticks:
            score += 1

        if (
            signal.pre.close_odds > 1.0
            and signal.pre.close_odds <= cfg.close_odds_strength_threshold
        ):
            score += 1

        if signal.pre.consensus_strength >= cfg.consensus_threshold:
            score += 1

        if signal.pre.close_price_quality.lower() == "good":
            score += 1

        return score

    def build_reversion_score(self, signal: SignalInput, reversion_ticks: int) -> int:
        score = 0
        cfg = self.config.reversion

        if reversion_ticks >= cfg.strong_reversion_ticks:
            score += 2
        elif reversion_ticks >= cfg.weak_reversion_ticks:
            score += 1

        minute = signal.live.minute
        if cfg.prime_window_start <= minute <= cfg.prime_window_end:
            score += 2
        elif cfg.prime_window_end < minute <= cfg.secondary_window_end:
            score += 1

        return score

    def build_state_score(self, signal: SignalInput) -> int:
        score = 0
        state = signal.state
        live = signal.live

        if state.red_cards_total == 0:
            score += 1
        if live.total_goals == 0:
            score += 1
        if not state.favorite_under_heavy_pressure:
            score += 1
        if not state.is_post_suspend_noise:
            score += 1

        return score

    def build_penalty_score(self, signal: SignalInput) -> int:
        penalty = 0
        state = signal.state

        if state.hard_negative_event:
            penalty += 3
        if state.market_trending_against_signal:
            penalty += 2
        if state.reversion_explained_by_time_decay_only:
            penalty += 2

        return penalty

    def build_edge_score(self, edge_after_cost: float) -> int:
        cfg = self.config.edge
        if edge_after_cost >= cfg.strong_edge:
            return 2
        if edge_after_cost >= cfg.medium_edge:
            return 1
        return 0

    def _compute_line_move_ticks(self, signal: SignalInput, direction: int) -> int:
        if signal.pre.line_move_ticks is not None:
            return max(signal.pre.line_move_ticks, 0)

        open_ticks = _line_to_ticks(signal.pre.open_line)
        close_ticks = _line_to_ticks(signal.pre.close_line)
        return max(direction * (close_ticks - open_ticks), 0)

    def _compute_reversion_ticks(self, signal: SignalInput, direction: int) -> int:
        close_ticks = _line_to_ticks(signal.pre.close_line)
        live_ticks = _line_to_ticks(signal.live.live_line)
        return max(direction * (close_ticks - live_ticks), 0)

    def _compute_fair_odds(
        self, signal: SignalInput, pre_score: int, state_score: int
    ) -> float:
        model = signal.model

        if model.fair_odds is not None and model.fair_odds > 1.0:
            return model.fair_odds
        if model.fair_prob is not None and model.fair_prob > 0:
            return 1.0 / model.fair_prob

        # No explicit model input: use market odds as base and apply tiny shrinkage by state quality.
        adjustment = 1.0 + min((pre_score + state_score) * 0.005, 0.03)
        return signal.live.live_back_odds / adjustment

    def _signal_label(self, market_type: MarketType) -> str:
        if market_type == MarketType.AH:
            return "AH_OVER_REVERSION"
        if market_type == MarketType.OU:
            return "OU_OVER_REVERSION"
        if market_type == MarketType.TEAM_TOTAL:
            return "TT_OVER_REVERSION"
        if market_type == MarketType.ONE_X_TWO:
            return "ONE_X_TWO_OVER_REVERSION"
        if market_type == MarketType.DNB:
            return "DNB_OVER_REVERSION"
        if market_type == MarketType.DOUBLE_CHANCE:
            return "DOUBLE_CHANCE_OVER_REVERSION"
        return "HALF_TIME_OVER_REVERSION"

    def evaluate(self, signal: SignalInput) -> SignalEvaluation:
        filter_result = self.hard_filter.evaluate(signal, self.config)
        if not filter_result.passed:
            return SignalEvaluation(
                accepted=False,
                reason=";".join(filter_result.reasons),
                signal_label=self._signal_label(signal.pre.market_type),
                signal_score=0,
                level="D",
                pre_signal_score=0,
                reversion_score=0,
                state_score=0,
                penalty_score=0,
                edge_score=0,
                line_move_ticks=0,
                reversion_ticks=0,
                edge_raw=0.0,
                edge_after_cost=0.0,
                fair_odds=0.0,
                market_stable=False,
            )

        direction = _normalize_direction(signal)
        line_move_ticks = self._compute_line_move_ticks(signal, direction)
        reversion_ticks = self._compute_reversion_ticks(signal, direction)

        pre_score = self.build_pre_signal_score(signal, line_move_ticks)
        rev_score = self.build_reversion_score(signal, reversion_ticks)
        state_score = self.build_state_score(signal)
        penalty_score = self.build_penalty_score(signal)

        fair_odds = _safe_odds(
            self._compute_fair_odds(signal, pre_score, state_score),
            fallback=signal.live.live_back_odds,
        )
        edge_raw = signal.live.live_back_odds / fair_odds - 1.0
        cost_bps = (
            signal.model.cost_bps
            if signal.model.cost_bps is not None
            else self.config.edge.default_cost_bps
        )
        edge_after_cost = edge_raw - (cost_bps / 10000.0)
        edge_score = self.build_edge_score(edge_after_cost)

        total = pre_score + rev_score + state_score + edge_score - penalty_score
        if total >= 8:
            level = "A"
        elif total >= 6:
            level = "B"
        elif total >= 4:
            level = "C"
        else:
            level = "D"

        accepted = (
            total >= self.config.signal.min_total_score
            and pre_score >= self.config.pre_signal.min_pre_score
            and reversion_ticks >= self.config.reversion.weak_reversion_ticks
            and edge_after_cost >= self.config.edge.min_edge_after_cost
        )

        return SignalEvaluation(
            accepted=accepted,
            reason=None if accepted else "score_or_edge_below_threshold",
            signal_label=self._signal_label(signal.pre.market_type),
            signal_score=total,
            level=level,
            pre_signal_score=pre_score,
            reversion_score=rev_score,
            state_score=state_score,
            penalty_score=penalty_score,
            edge_score=edge_score,
            line_move_ticks=line_move_ticks,
            reversion_ticks=reversion_ticks,
            edge_raw=edge_raw,
            edge_after_cost=edge_after_cost,
            fair_odds=fair_odds,
            market_stable=True,
        )

