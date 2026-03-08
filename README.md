# cloudbettrend

`cloudbettrend` 是一个足球盘口研究框架 v1，核心是：

**赛前强信息 + 滚球早段过度回盘 + 状态未证伪 + 市场稳定 + 价格有 edge**

当前版本支持：

- 统一数据模型（AH / OU / Team Total / 1X2 等）
- 统一信号评分引擎
- 硬过滤器（红牌、暂停恢复噪声、盘口跳线、比分条件等）
- 风控管理（单笔上限、日亏损上限、硬回撤熔断、连亏限制、日交易次数限制）
- 资金管理（分级 fractional Kelly + 波动目标 + 回撤/连亏动态降杠杆）
- 简单回测流水线（JSONL/CSV -> 信号 -> 统计 -> 可选 CSV 输出）
- SQLite 表结构脚本（赛前/滚球/状态/模型/执行/结果字段）

## 1. 安装

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .[dev]
```

## 2. 运行示例回测

```bash
cloudbettrend backtest \
  --input examples/sample_signals.jsonl \
  --config configs/default.yaml \
  --output out/signals.csv
```

## 3. 跑测试

```bash
pytest -q
```

## 4. Cloudbet 盘口变动扫描

1) 先采集盘口快照（建议每 30-60 秒跑一次定时任务）：

```bash
set CLOUDBET_API_KEY=your_api_key
cloudbettrend collect-cloudbet ^
  --competition soccer-england-premier-league ^
  --db data/cloudbet_lines.db
```

2) 检测赛前升/降两个盘口（默认 2 ticks = 0.5）：

```bash
cloudbettrend detect-line-moves ^
  --db data/cloudbet_lines.db ^
  --min-ticks 2 ^
  --lookback-hours 48 ^
  --output out/line_moves.csv
```

如需临时包含开赛后盘口变化（用于调试/观察，不是纯赛前研究），加 `--include-live`。

3) 一条命令采集并扫描：

```bash
cloudbettrend cloudbet-scan ^
  --competition soccer-england-premier-league ^
  --db data/cloudbet_lines.db ^
  --min-ticks 2
```

## 5. 目录说明

- `src/cloudbettrend/models.py`: 数据结构
- `src/cloudbettrend/filters.py`: 统一过滤器
- `src/cloudbettrend/scoring.py`: 评分引擎
- `src/cloudbettrend/risk.py`: 风控引擎与资金状态
- `src/cloudbettrend/bankroll.py`: 仓位建议引擎
- `src/cloudbettrend/backtest.py`: 回测流程
- `src/cloudbettrend/cloudbet_feed.py`: Cloudbet API 接口封装
- `src/cloudbettrend/line_moves.py`: 赛前盘口快照与两档变动检测
- `configs/default.yaml`: 默认参数
- `sql/schema.sql`: SQLite 表结构

## 6. Over-Reversion 信号

检测逻辑：

- 赛前从 open 到 close 移动 >= 2 ticks
- 开赛后早段（默认 25 分钟内）盘口回到 open 附近
- 输出建议方向：
  - `soccer.total_goals`: pre 上升后回落到 open/更低 -> `bet_side=over`
  - `soccer.asian_handicap`: 主队让球 pre 加深后回到 open/更浅 -> `bet_side=home`

命令：

```bash
cloudbettrend detect-overreversion \
  --db data/cloudbet_lines.db \
  --lookback-hours 96 \
  --min-pre-move-ticks 2 \
  --min-reversion-ticks 1 \
  --max-live-minutes 25 \
  --output out/over_reversion_signals.csv
```
