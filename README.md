# Gold Quantitative Analysis

实时黄金价格数据采集系统，支持定时抓取、SQLite 存储，可用于后续量化分析。

## 数据源

API: `api.jijinhao.com` 实时黄金行情接口，每 2-3 秒采集一次。

## 快速开始

```bash
# 创建虚拟环境并安装依赖
uv venv
source .venv/bin/activate
uv sync

# 运行采集器
python -m src.collector
```

按 `Ctrl+C` 优雅停止。

## 项目结构

```
├── pyproject.toml          # 项目配置与依赖
├── schema.sql              # SQLite 表结构参考
├── data/
│   └── gold.db             # SQLite 数据库（自动生成）
└── src/
    ├── config.py           # 配置（API URL、请求头、采集间隔）
    ├── parser.py           # API 响应解析
    ├── db.py               # SQLite 数据库模块
    └── collector.py        # 主采集循环
```

## 数据表

`gold_prices` 表字段：

| 字段 | 说明 |
|---|---|
| fetched_at | 采集时间 (UTC+8) |
| current_price | 当前金价 |
| max_today | 今日最高 |
| min_today | 今日最低 |
| open_price | 今日开盘 |
| quote_date / quote_time | 数据源的日期时间 |

## 依赖

- Python >= 3.11
- httpx
