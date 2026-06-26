# Gold Quantitative Analysis

实时黄金价格数据采集 + 技术指标分析 + 交易信号系统。轮询 `api.jijinhao.com` 黄金行情接口，每 2-3 秒采集一次，解析响应后存入 SQLite，计算技术指标（SMA、EMA、RSI、布林带、MACD），生成 BUY/SELL/HOLD 共识信号。

## 快速开始

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
uv sync

# 1. 启动采集器（持续采集数据）
uv run python -m src.collector

# 2. 另开终端，启动信号监控
#    终端模式：
uv run python -m src.cli_signal
#    Web 仪表板模式：
PYTHONPATH=. uv run streamlit run src/streamlit_app.py
```

按 `Ctrl+C` 优雅停止。

## 模块说明

```
src/
├── collector.py              # 数据采集主循环（asyncio）
├── parser.py                 # API 响应解析（var hq_str = "..." 格式）
├── db.py                     # SQLite 存储（WAL 模式）
├── config.py                 # 配置常量（URL、请求头、轮询间隔）
├── analyst/                  # 信号分析模块
│   ├── __init__.py           #   模块入口，导出核心函数和类
│   ├── indicators.py         #   SMA, EMA, RSI, Bollinger Bands, MACD
│   ├── signals.py            #   买卖规则 + 信号聚合
│   └── engine.py             #   核心引擎：DB → K线 → 指标 → 信号
├── cli_signal.py             # 终端实时信号监控（rich）
└── streamlit_app.py          # Streamlit 仪表板（Altair 图表）
```

### 模块详细说明

- **`collector.py`** — asyncio 主循环。创建 `httpx.AsyncClient`，以 2-3 秒随机间隔轮询。注册 SIGINT/SIGTERM 信号处理器实现优雅关闭。每个周期：请求 → 解析 → 日志 → 存储。单周期异常不影响整体运行。
- **`parser.py`** — 解析 `var hq_str = "..."` 格式的 API 响应。通过字符串前缀/后缀裁剪 + CSV 分割提取字段，日期/时间字段用正则匹配。解析异常时抛出 `ParseError`。
- **`db.py`** — SQLite 数据库访问。WAL 模式 + NORMAL 同步，平衡写入性能与数据安全性。模块级 `_DB_PATH` 由 `init_db()` 设置。
- **`config.py`** — 常量定义：API URL 模板、请求头、轮询间隔范围（2-3 秒）、数据库路径。无敏感信息。
- **`analyst/indicators.py`** — 纯指标计算函数：`sma()`、`ema()`、`rsi()`、`bollinger_bands()`、`macd()`。返回值与输入对齐（不足周期处填充 `None`）。
- **`analyst/signals.py`** — 四种信号策略评估：SMA 金叉/死叉、RSI 超买/超卖、布林带触碰、MACD 交叉。`aggregate_signals()` 投票产生最终共识。
- **`analyst/engine.py`** — `SignalEngine` 类：连接 DB → 读取原始 tick → 去重 → 聚合 1 分钟 OHLC K 线 → 计算指标 → 评估信号。支持全量 `refresh()` 和增量 `tick()`，返回包含 K 线、指标、信号、共识的快照。
- **`cli_signal.py`** — 终端 UI，基于 `rich` 的实时显示。展示最近 20 根分钟 K 线及指标值，底部显示活跃信号和共识。
- **`streamlit_app.py`** — Web 仪表板。包含价格走势图（SMA + 布林带叠加）、RSI 图（超买/超卖线）、MACD 图、信号历史表格。每 2 秒自动刷新。

## 数据流

1. `collector.poll_once()` 记录采集时间（UTC+8），调用 `fetch_price()`（带毫秒级缓存破坏参数）
2. 原始字符串经 `parser.parse_response()` 解析，提取 `current_price`、`open_price`、`max_today`、`min_today`、`quote_date`、`quote_time`
3. `db.insert_record()` 写入一行到 `data/gold.db` 的 `gold_prices` 表
4. `SignalEngine` 从 DB 读取原始 tick，按 (date, time) 去重，聚合成 1 分钟 OHLC K 线
5. 基于 K 线收盘价计算技术指标
6. 信号策略评估指标值，投票产生共识

## 交易信号

| 信号 | 买入 | 卖出 |
|------|------|------|
| SMA 金叉/死叉 | SMA5 上穿 SMA20 | SMA5 下穿 SMA20 |
| RSI 超买/超卖 | < 30（超卖） | > 70（超买） |
| 布林带 | 触碰下轨 | 触碰上轨 |
| MACD | MACD 线上穿信号线 | MACD 线下穿信号线 |

四种信号投票产生最终共识 **BUY** / **SELL** / **HOLD**。信号强度基于偏离程度计算（0.0 ~ 1.0）。

### 共识规则

- 买入票数 > 卖出票数 且 买入总强度 > 0.3 → **BUY**
- 卖出票数 > 买入票数 且 卖出总强度 > 0.3 → **SELL**
- 否则 → **HOLD**

## 数据表

### `gold_prices`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键自增 |
| fetched_at | TEXT | 采集时间 (UTC+8, ISO 8601) |
| quote_date | TEXT | 数据源日期（如 "2026-06-25"） |
| quote_time | TEXT | 数据源时间（如 "09:16:14"） |
| open_price | REAL | 今日开盘价 |
| current_price | REAL | 当前/最新价 |
| max_today | REAL | 今日最高价 |
| min_today | REAL | 今日最低价 |
| raw_response | TEXT | 原始 API 响应（可回放解析） |
| created_at | TEXT | 记录创建时间 (UTC+8) |

## 项目结构

```
├── pyproject.toml              # 项目配置与依赖管理
├── CLAUDE.md                   # Claude Code AI 辅助开发指南
├── schema.sql                  # SQLite 表结构 DDL（参考用，由代码自动建表）
├── data/
│   └── gold.db                 # SQLite 数据库文件（运行后自动生成）
└── src/
    ├── __init__.py             # 包标识，使 src 可作为 Python 模块导入
    ├── config.py               # 全局常量：API URL 模板、请求头、轮询间隔(2-3s)、DB 路径
    ├── collector.py            # 数据采集主循环，asyncio 异步轮询，随机间隔 2-3s，
    │                           #   注册 SIGINT/SIGTERM 实现优雅关闭
    ├── parser.py               # API 响应解析，处理 var hq_str = "..." 格式，
    │                           #   按 CSV 分割字段 + 正则提取日期时间
    ├── db.py                   # SQLite 存储层，WAL 模式 + NORMAL 同步，
    │                           #   提供 init_db() / insert_record() 接口
    ├── analyst/
    │   ├── __init__.py         # 模块入口，导出 sma/ema/rsi/bollinger_bands/macd/
    │   │                       #   evaluate_signals/aggregate_signals/SignalEngine
    │   ├── indicators.py       # 技术指标纯函数计算：sma(), ema(), rsi(),
    │   │                       #   bollinger_bands(), macd()，不足周期填充 None
    │   ├── signals.py          # 信号策略：SMA 金叉/死叉、RSI 阈值、布林带 %B、
    │   │                       #   MACD 交叉，aggregate_signals() 投票聚合共识
    │   └── engine.py           # SignalEngine 核心引擎：连接 DB → 读取 ticks →
    │                           #   去重 → 1min OHLC K 线 → 指标 → 信号 →
    │                           #   快照输出，支持全量 refresh() 和增量 tick()
    ├── cli_signal.py           # 终端实时信号监控，基于 rich 的 Live 显示，
    │                           #   展示最近 20 根 K 线 + 指标值 + 活跃信号 + 共识
    └── streamlit_app.py        # Streamlit Web 仪表板，Altair 图表展示价格走势
                                #   (SMA+BB 叠加)、RSI(超买/超卖线)、MACD、
                                #   信号历史表格，每 2s 自动刷新
```

## 依赖

- Python >= 3.11
- httpx — HTTP 客户端（异步）
- rich — 终端格式化
- streamlit — Web 仪表板
- altair — 图表（声明式统计可视化）

通过 `uv` 和 `pyproject.toml` 管理依赖。

### Signal

```
  现在出现了重要变化——刚刚在 22:39 产生了 SMA5 下穿 SMA20（死叉） 信号，系统发出 SELL。
  但是注意看 RSI 只有 56.7（中性），布林带 %B=0.42（也中性），4 个策略里只有 1 个看跌，共识还是 HOLD。
  按系统的规则，什么时候该买？

  系统要出现 4 个策略里有 3 个以上 BUY 才真正值得出手。具体触发条件：
  ┌──────────┬─────────────────────────────────────────┬───────────────────────┐                                            
  │   策略   │                买入条件                 │       当前状态        │                                            
  ├──────────┼─────────────────────────────────────────┼───────────────────────┤                                            
  │ SMA 交叉 │ SMA5 上穿 SMA20（金叉）                 │ ❌ 现在是死叉（SELL） │                                            
  ├──────────┼─────────────────────────────────────────┼───────────────────────┤                                            
  │ RSI      │ RSI 跌到 30 以下（超卖）                │ ❌ RSI 56.7，还远     │                                            
  ├──────────┼─────────────────────────────────────────┼───────────────────────┤                                            
  │ 布林带   │ 价格跌破下轨后回到轨道内（%B 从负转正） │ ❌ %B=0.42，在中间    │                                            
  ├──────────┼─────────────────────────────────────────┼───────────────────────┤                                            
  │ MACD     │ MACD 线在零轴下上穿信号线               │ ❌ 数据还不够         │                                            
  └──────────┴─────────────────────────────────────────┴───────────────────────┘                                            

  一句话规则
  ▎ 4 个策略里 >= 3 个喊 BUY 就买，>= 3 个喊 SELL 就卖，其他情况不动。                                                      
  目前 SMA 喊跌，其他三个都喊 HOLD，所以共识是 持有不动。真正的买入机会要等价格回调到 RSI < 30 或布林下轨附近 + SMA 重新金叉时才会出现。
  建议用 uv run python -m src.cli_signal 开终端监控，盯着 RSI 和 SMA 信号变化最重要。
```