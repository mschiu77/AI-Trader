# 台湾证交所 (TWSE) 交易策略配置

本指南介绍如何使用 AI-Trader 系统配置和运行台湾证交所 (TWSE) 的交易策略。

## 1. 数据源

系统已更新为从 `mis.twse.com.tw` (实时/每日快照) 获取数据，不再使用 Alpha Vantage。

-   **获取脚本:** `data/TW_stock/get_daily_price_tw.py`
    -   获取被追踪 TWSE 股票的最新每日快照。
    -   处理台湾加权指数的特殊情况 (`^TWII` -> `tse_t00.tw`)。
-   **合并脚本:** `data/TW_stock/merge_jsonl_tw.py`
    -   将各个股票的 JSON 文件合并为 `data/TW_stock/merged.jsonl`，供交易 Agent 使用。

## 2. 配置文件

定义交易参数的主要方式是通过配置 JSON 文件。我们已为 TWSE 创建了一个专用文件：`configs/tw_stock_config.json`。

### 关键参数：

*   **`market`**: 必须设置为 `"tw"`。这确保 Agent 使用 TWSE 特有的逻辑（例如：1手 = 1000股）。
*   **`initial_cash`**: 设置您的初始资金，单位为新台币 (TWD)（例如：`1000000.0`）。
*   **`date_range`**: 定义回测/模拟的开始和结束日期。
    -   `init_date`: 开始日期 (YYYY-MM-DD)。
    -   `end_date`: 结束日期 (YYYY-MM-DD)。
*   **`models`**: 选择驱动 Agent 的 AI 模型。
    -   `name`: 显示名称。
    -   `basemodel`: 底层 LLM（例如：`openai/gpt-5`）。
    -   `signature`: 实验运行的唯一标识符。

**`configs/tw_stock_config.json` 示例:**

```json
{
  "agent_type": "BaseAgent",
  "market": "tw",
  "date_range": {
    "init_date": "2026-02-01",
    "end_date": "2026-02-28"
  },
  "models": [
    {
      "name": "gpt-5",
      "basemodel": "openai/gpt-5",
      "signature": "gpt-5-tw-strategy",
      "enabled": true
    }
  ],
  "agent_config": {
    "max_steps": 20,
    "max_retries": 3,
    "base_delay": 1.0,
    "initial_cash": 1000000.0,
    "verbose": true
  },
  "log_config": {
    "log_path": "./data/agent_data_twstock"
  }
}
```

## 3. 自定义策略逻辑

要实施特定的交易策略（例如：“价值投资”、“动量交易”），您需要修改 **系统提示词 (System Prompt)**。

-   **文件:** `prompts/agent_prompt.py`
-   **变量:** `agent_system_prompt`

您可以编辑 `agent_system_prompt` 中的文本，向 AI 发出具体指令。

**修改示例:**

```python
agent_system_prompt = """
你是一位专注于股息收益率和稳定性的保守型投资者。

策略规则：
1. 只买入市盈率 (P/E) 低于 20 的股票（你需要使用搜索工具来查找此信息）。
2. 优先考虑像台积电 (2330) 或联发科 (2454) 这样的行业龙头。
3. 单只股票的持仓比例不要超过投资组合的 20%。
4. 如果某只股票从你的买入价下跌 10%，立即卖出（止损）。

... (提示词的其余部分)
"""
```

## 4. 运行 Agent

更新数据和配置后，通过以下命令运行 Agent：

```bash
# 1. 更新数据 (可选，如果今天需要最新数据)
python3 data/TW_stock/get_daily_price_tw.py
python3 data/TW_stock/merge_jsonl_tw.py

# 2. 运行交易模拟
python3 main.py configs/tw_stock_config.json
```

## 5. 查看结果

Agent 的活动和日志将保存到 `log_path` 指定的路径中（默认：`./data/agent_data_twstock`）。

-   **日志:** `data/agent_data_twstock/<signature>/log/`
-   **持仓:** `data/agent_data_twstock/<signature>/position/position.jsonl`
