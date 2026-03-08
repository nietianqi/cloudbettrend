from __future__ import annotations

from dataclasses import dataclass

from .config import EngineConfig
from .models import MarketType, SignalInput


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    reasons: list[str]


def _favorite_diffs(signal: SignalInput) -> tuple[int, int, int, float]:
    """Return (shots_diff, sot_diff, corners_diff, danger_ratio) from the favorite's POV."""
    side = signal.favorite_side.lower()
    s = signal.state

    if side == "away":
        shots_diff = s.shots_away - s.shots_home
        shots_on_target_diff = s.shots_on_target_away - s.shots_on_target_home
        corners_diff = s.corners_away - s.corners_home
        fav_danger = float(s.dangerous_attacks_away)
        opp_danger = float(s.dangerous_attacks_home)
    else:
        shots_diff = s.shots_home - s.shots_away
        shots_on_target_diff = s.shots_on_target_home - s.shots_on_target_away
        corners_diff = s.corners_home - s.corners_away
        fav_danger = float(s.dangerous_attacks_home)
        opp_danger = float(s.dangerous_attacks_away)

    total_danger = fav_danger + opp_danger
    danger_ratio = 0.5 if total_danger <= 0 else fav_danger / total_danger
    return shots_diff, shots_on_target_diff, corners_diff, danger_ratio


# Market types where favorite-side dominance metrics apply
_DIRECTIONAL_MARKETS = {
    MarketType.AH,
    MarketType.TEAM_TOTAL,
    MarketType.ONE_X_TWO,
    MarketType.DNB,
    MarketType.DOUBLE_CHANCE,
    MarketType.HALF_TIME,
}

# Market types where total-game tempo metrics apply
_TEMPO_MARKETS = {MarketType.OU, MarketType.TEAM_TOTAL}


class HardFilter:
    def evaluate(self, signal: SignalInput, config: EngineConfig) -> FilterResult:
        reasons: list[str] = []
        live = signal.live
        state = signal.state
        st_cfg = config.market_stability
        sig_cfg = config.signal
        state_cfg = config.state

        # --- Time window ---
        if live.minute < sig_cfg.minute_start or live.minute > sig_cfg.minute_end:
            reasons.append("minute_out_of_window")

        # --- Score state ---
        if sig_cfg.require_neutral_score and live.total_goals > 0:
            reasons.append("score_not_neutral")

        # --- Cards & injuries ---
        if not sig_cfg.allow_red_cards and state.red_cards_total > 0:
            reasons.append("red_card_present")

        if state.hard_negative_event:
            reasons.append("hard_negative_event")
        if state.injury_flag_home or state.injury_flag_away:
            reasons.append("injury_flag_present")

        # --- Market stability ---
        if st_cfg.require_open_status and live.market_status.upper() != "OPEN":
            reasons.append("market_not_open")

        if (
            live.seconds_since_reopen is not None
            and live.seconds_since_reopen < st_cfg.min_seconds_since_reopen
        ):
            reasons.append("post_reopen_noise")

        if live.line_jump_count_last_60s > st_cfg.max_line_jumps_last_60s:
            reasons.append("line_too_jumpy")
        if live.odds_jump_count_last_60s > st_cfg.max_odds_jumps_last_60s:
            reasons.append("odds_too_jumpy")

        if live.max_stake is not None and live.max_stake < st_cfg.min_max_stake:
            reasons.append("max_stake_too_low")

        # --- Directional market: favorite-side dominance metrics ---
        # FIX A3: _favorite_diffs is only called when actually needed
        if signal.pre.market_type in _DIRECTIONAL_MARKETS:
            shots_diff, shots_on_target_diff, corners_diff, danger_ratio = (
                _favorite_diffs(signal)
            )
            if shots_diff < state_cfg.min_shots_diff_fav:
                reasons.append("favorite_shots_too_weak")
            if shots_on_target_diff < state_cfg.min_shots_on_target_diff_fav:
                reasons.append("favorite_sot_too_weak")
            if corners_diff < state_cfg.min_corners_diff_fav:
                reasons.append("favorite_corners_too_weak")
            if danger_ratio < state_cfg.min_dangerous_attacks_ratio_fav:
                reasons.append("favorite_danger_ratio_too_low")

        # --- Tempo markets: total-game pace metrics after minute 12 ---
        if signal.pre.market_type in _TEMPO_MARKETS and live.minute >= 12:
            total_shots = state.shots_home + state.shots_away
            total_danger = state.dangerous_attacks_home + state.dangerous_attacks_away
            if total_shots < state_cfg.min_total_shots_for_ou_after_12:
                reasons.append("tempo_too_slow_shots")
            if total_danger < state_cfg.min_total_dangerous_attacks_for_ou_after_12:
                reasons.append("tempo_too_slow_danger")

        return FilterResult(passed=not reasons, reasons=reasons)
