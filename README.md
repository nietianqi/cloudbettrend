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

## 4. 目录说明

- `src/cloudbettrend/models.py`: 数据结构
- `src/cloudbettrend/filters.py`: 统一过滤器
- `src/cloudbettrend/scoring.py`: 评分引擎
- `src/cloudbettrend/risk.py`: 风控引擎与资金状态
- `src/cloudbettrend/bankroll.py`: 仓位建议引擎
- `src/cloudbettrend/backtest.py`: 回测流程
- `configs/default.yaml`: 默认参数
- `sql/schema.sql`: SQLite 表结构
