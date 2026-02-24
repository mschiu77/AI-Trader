# TWSE Trading Strategy Configuration

This guide explains how to configure and run trading strategies for the Taiwan Stock Exchange (TWSE) using the AI-Trader system.

## 1. Data Source

The system has been updated to fetch data from `mis.twse.com.tw` (real-time/daily snapshot) instead of Alpha Vantage.

-   **Fetch Script:** `data/TW_stock/get_daily_price_tw.py`
    -   Fetches the latest daily snapshot for tracked TWSE stocks.
    -   Handles the special case for the Taiwan Weighted Index (`^TWII` -> `tse_t00.tw`).
-   **Merge Script:** `data/TW_stock/merge_jsonl_tw.py`
    -   Merges individual stock JSON files into `data/TW_stock/merged.jsonl`, which is used by the trading agent.

## 2. Configuration File

The primary way to define your trading parameters is through a configuration JSON file. A dedicated file for TWSE has been created at `configs/tw_stock_config.json`.

### Key Parameters:

*   **`market`**: Must be set to `"tw"`. This ensures the agent uses TWSE-specific logic (e.g., 1 lot = 1000 shares).
*   **`initial_cash`**: Set your starting capital in TWD (e.g., `1000000.0`).
*   **`date_range`**: Define the start and end dates for the backtest/simulation.
    *   `init_date`: Start date (YYYY-MM-DD).
    *   `end_date`: End date (YYYY-MM-DD).
*   **`models`**: Select the AI model to drive the agent.
    *   `name`: Display name.
    *   `basemodel`: The underlying LLM (e.g., `openai/gpt-5`).
    *   `signature`: Unique identifier for the experiment run.

**Example `configs/tw_stock_config.json`:**

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

## 3. Customizing Strategy Logic

To implement a specific trading strategy (e.g., "Value Investing", "Momentum Trading"), you need to modify the **System Prompt**.

-   **File:** `prompts/agent_prompt.py`
-   **Variable:** `agent_system_prompt`

You can edit the text within `agent_system_prompt` to give specific instructions to the AI.

**Example Modification:**

```python
agent_system_prompt = """
You are a conservative investor focusing on dividend yield and stability.

Strategy Rules:
1. Only buy stocks with a P/E ratio under 20 (you will need to use search tools to find this).
2. Prioritize sector leaders like TSMC (2330) or MediaTek (2454).
3. Do not hold more than 20% of your portfolio in a single stock.
4. If a stock drops 10% from your buy price, sell immediately (Stop Loss).

... (rest of the prompt)
"""
```

## 4. Running the Agent

Once you have updated the data and configuration, run the agent with:

```bash
# 1. Update Data (Optional, if needed for today)
python3 data/TW_stock/get_daily_price_tw.py
python3 data/TW_stock/merge_jsonl_tw.py

# 2. Run Trading Simulation
python3 main.py configs/tw_stock_config.json
```

## 5. Viewing Results

The agent's activity and logs will be saved to the path specified in `log_path` (default: `./data/agent_data_twstock`).

-   **Logs:** `data/agent_data_twstock/<signature>/log/`
-   **Positions:** `data/agent_data_twstock/<signature>/position/position.jsonl`
