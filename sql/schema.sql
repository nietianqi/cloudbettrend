PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS signal_samples (
  sample_id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- A. 赛前字段
  match_id TEXT NOT NULL,
  league TEXT,
  kickoff_time TEXT,
  home_team TEXT,
  away_team TEXT,
  market_type TEXT NOT NULL,
  open_line REAL,
  open_odds REAL,
  close_line REAL,
  close_odds REAL,
  line_move_ticks INTEGER,
  odds_move_bps REAL,
  consensus_strength REAL,
  close_snapshot_time TEXT,

  -- B. 滚球时点字段
  signal_time TEXT,
  minute INTEGER,
  second INTEGER,
  score_home INTEGER,
  score_away INTEGER,
  live_line REAL,
  live_back_odds REAL,
  live_lay_odds REAL,
  live_spread REAL,
  max_stake REAL,
  market_status TEXT,
  seconds_since_reopen INTEGER,
  line_jump_count_last_60s INTEGER,
  odds_jump_count_last_60s INTEGER,

  -- C. 比赛状态字段
  red_home INTEGER,
  red_away INTEGER,
  yellow_home INTEGER,
  yellow_away INTEGER,
  shots_home INTEGER,
  shots_away INTEGER,
  shots_on_target_home INTEGER,
  shots_on_target_away INTEGER,
  dangerous_attacks_home INTEGER,
  dangerous_attacks_away INTEGER,
  corners_home INTEGER,
  corners_away INTEGER,
  possession_home REAL,
  possession_away REAL,
  attacks_home INTEGER,
  attacks_away INTEGER,
  injury_flag_home INTEGER,
  injury_flag_away INTEGER,

  -- D. 模型字段
  pre_signal_score REAL,
  reversion_ticks INTEGER,
  state_support_score REAL,
  fair_prob REAL,
  fair_odds REAL,
  market_prob REAL,
  edge_raw REAL,
  edge_after_cost REAL,
  signal_label TEXT,

  -- E. 执行字段
  intended_stake REAL,
  proposed_stake REAL,
  allowed_stake REAL,
  matched_stake REAL,
  stake_fraction REAL,
  full_kelly_fraction REAL,
  placed_odds REAL,
  matched_odds REAL,
  rejected_flag INTEGER,
  slippage_bps REAL,
  execution_delay_ms INTEGER,
  risk_allowed INTEGER,
  risk_reason TEXT,
  risk_stake_cap REAL,
  risk_level TEXT,               -- signal quality level passed to RiskManager
  soft_drawdown_active INTEGER,  -- 1 if soft drawdown warning was active at execution
  bankroll_before REAL,
  bankroll_after REAL,
  drawdown_ratio REAL,
  -- Bankroll scaling factors
  volatility_scale REAL,
  drawdown_scale REAL,
  level_scale REAL,
  streak_scale REAL,
  market_type_scale REAL,        -- per-market-type Kelly adjustment
  uncertainty_scale REAL,        -- fair_odds estimation quality discount
  clv_feedback_scale REAL,       -- CLV feedback loop scale

  -- F. 结果字段
  final_score_home INTEGER,
  final_score_away INTEGER,
  outcome_winlosepush TEXT,
  pnl REAL,
  closing_line_after_1m REAL,
  closing_line_after_3m REAL,
  closing_odds_after_1m REAL,
  closing_odds_after_3m REAL,
  clv_bps REAL,

  -- G. 组合状态字段
  weekly_pnl REAL,               -- cumulative PnL for current ISO week
  monthly_pnl REAL               -- cumulative PnL for current calendar month
);

CREATE INDEX IF NOT EXISTS idx_signal_samples_match ON signal_samples(match_id);
CREATE INDEX IF NOT EXISTS idx_signal_samples_market ON signal_samples(market_type, minute);
CREATE INDEX IF NOT EXISTS idx_signal_samples_signal ON signal_samples(signal_label, edge_after_cost);
CREATE INDEX IF NOT EXISTS idx_signal_samples_week ON signal_samples(kickoff_time, weekly_pnl);
