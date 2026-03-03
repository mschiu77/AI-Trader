"""
TW Stock Agent Prompt Module
"""

import os
import sys
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.general_tools import get_config_value
from tools.price_tools import (
    format_price_dict_with_names,
    get_open_prices,
    get_today_init_position,
    get_yesterday_open_and_close_price,
    get_yesterday_profit,
)

# Import TW50 symbols
try:
    from data.TW_stock.get_daily_price_tw import tw_50_codes
except ImportError:
    # Fallback if import fails
    tw_50_codes = ["2330.TW", "2317.TW", "2454.TW", "2308.TW", "2881.TW"]

STOP_SIGNAL = "<FINISH_SIGNAL>"

agent_system_prompt_twstock = """
You are a Taiwan Stock Market Analysis and Trading Assistant.

Your Goal:
- Analyze stock prices and trends using available tools.
- Maximize portfolio returns over the long term.
- Collect information via search tools before making decisions.

Thinking Standards:
- Clearly show key intermediate steps:
  - Read current positions and prices.
  - Update valuations and adjust target weights.

Important Instructions:
- You do not need user permission to execute trades.
- You MUST call tools to execute actions (buy/sell).
- **The market is OPEN, you can execute real trades.**

⚠️ Critical Requirements:
1. **Must actually call buy() or sell() tools**, do not just give advice.
2. **Do not fabricate errors**.
3. **Do not assume limitations** like "System restriction" or "Symbol not found" unless the tool returns an error.
4. **Directly call buy("2330.TW", quantity)** if you want to buy.
5. **Directly call sell("2330.TW", quantity)** if you want to sell.

🇹🇼 Taiwan Stock Market Rules:
1. **Symbol Format**: Must include .TW suffix (e.g., "2330.TW").
2. **Lot Size**: Standard lot is 1000 shares, but odd lots are allowed.
   - Example: buy("2330.TW", 1000) for 1 lot.
3. **Price Limits**: Generally ±10%.

Here is the information you need:

Current Date:
{date}

Current Positions (Number after symbol is shares held, CASH is available funds):
{positions}

Yesterday's Close Price (Reference):
{yesterday_close_price}

Current Buy Price (Today's Open):
{today_buy_price}

Previous Period Profit:
{current_profit}

When you believe the task is complete, output:
{STOP_SIGNAL}
"""


def get_agent_system_prompt_twstock(today_date: str, signature: str, stock_symbols: Optional[List[str]] = None) -> str:
    """
    Generate TW Stock System Prompt

    Args:
        today_date: Current date
        signature: Agent signature
        stock_symbols: List of stock symbols

    Returns:
        Formatted system prompt string
    """
    print(f"signature: {signature}")
    print(f"today_date: {today_date}")
    print(f"market: tw")

    if stock_symbols is None:
        stock_symbols = tw_50_codes

    # Get yesterday's prices
    yesterday_buy_prices, yesterday_sell_prices = get_yesterday_open_and_close_price(
        today_date, stock_symbols, market="tw"
    )
    # Get today's open price
    today_buy_price = get_open_prices(today_date, stock_symbols, market="tw")
    # Get current position
    today_init_position = get_today_init_position(today_date, signature)
    
    # Calculate profit
    current_profit = get_yesterday_profit(
        today_date, yesterday_buy_prices, yesterday_sell_prices, today_init_position, stock_symbols
    )

    # Format prices with names if possible (requires name mapping implementation for TW)
    # For now, it might just return symbols if names aren't mapped in price_tools
    yesterday_sell_prices_display = format_price_dict_with_names(yesterday_sell_prices, market="tw")
    today_buy_price_display = format_price_dict_with_names(today_buy_price, market="tw")

    return agent_system_prompt_twstock.format(
        date=today_date,
        positions=today_init_position,
        STOP_SIGNAL=STOP_SIGNAL,
        yesterday_close_price=yesterday_sell_prices_display,
        today_buy_price=today_buy_price_display,
        current_profit=current_profit,
    )

if __name__ == "__main__":
    today_date = get_config_value("TODAY_DATE")
    signature = get_config_value("SIGNATURE")
    if signature:
        print(get_agent_system_prompt_twstock(today_date, signature))
