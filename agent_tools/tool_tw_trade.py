import os
import sys
import json
import fcntl
from pathlib import Path
from typing import Any, Dict

from fastmcp import FastMCP

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from tools.general_tools import get_config_value, write_config_value
from tools.price_tools import get_latest_position, get_open_prices, get_yesterday_date

mcp = FastMCP("TWStockTradeTools")


def _position_lock(signature: str):
    """File-based lock to serialize position updates per signature."""
    class _Lock:
        def __init__(self, name: str):
            log_path = get_config_value("LOG_PATH", "./data/agent_data_twstock")
            if os.path.isabs(log_path):
                base_dir = Path(log_path) / name
            else:
                if log_path.startswith("./data/"):
                    log_rel = log_path[7:]
                else:
                    log_rel = log_path
                base_dir = Path(project_root) / "data" / log_rel / name
            base_dir.mkdir(parents=True, exist_ok=True)
            self.lock_path = base_dir / ".position.lock"
            self._fh = open(self.lock_path, "a+")

        def __enter__(self):
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            return self

        def __exit__(self, exc_type, exc, tb):
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()

    return _Lock(signature)


@mcp.tool()
def buy_tw(symbol: str, amount: int) -> Dict[str, Any]:
    """
    Buy Taiwan stock function (台灣股票買入)

    This function simulates Taiwan stock buying operations:
    1. Get current position and operation ID
    2. Get stock opening price for the day
    3. Validate buy conditions (sufficient cash, lot size)
    4. Update position (increase stock quantity, decrease cash)
    5. Record transaction to position.jsonl file

    Taiwan stock trading rules:
    - Symbols must end with '.TW' (TWSE) or '.TWO' (TPEx), e.g. '2330.TW' for TSMC
    - Minimum lot size: 1000 shares (一張 = 1000股)
    - Amount must be a multiple of 1000
    - No T+1 restriction (can sell same day you bought)
    - Daily price limit: ±10% from previous close

    Args:
        symbol: Taiwan stock symbol ending with '.TW' or '.TWO', e.g. '2330.TW', '2454.TW'
        amount: Number of shares to buy; must be a positive multiple of 1000

    Returns:
        Dict[str, Any]:
          - Success: Updated position dictionary (stock quantities and CASH balance in TWD)
          - Failure: {"error": error message, ...}

    Example:
        >>> result = buy_tw("2330.TW", 1000)   # Buy 1 lot of TSMC
        >>> result = buy_tw("2454.TW", 2000)   # Buy 2 lots of MediaTek
    """
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    today_date = get_config_value("TODAY_DATE")
    market = "tw"

    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return {
            "error": f"Invalid amount format. Amount must be an integer. You provided: {amount}",
            "symbol": symbol,
            "date": today_date,
        }

    if amount <= 0:
        return {
            "error": f"Amount must be positive. You tried to buy {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
        }

    # Taiwan trading rule: 1 lot = 1000 shares
    if amount % 1000 != 0:
        return {
            "error": (
                f"Taiwan stocks must be traded in multiples of 1000 shares (1 lot = 1000 shares). "
                f"You tried to buy {amount} shares."
            ),
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
            "suggestion": (
                f"Please use {(amount // 1000) * 1000} or {((amount // 1000) + 1) * 1000} shares instead."
            ),
        }

    with _position_lock(signature):
        try:
            current_position, current_action_id = get_latest_position(today_date, signature)
        except Exception as e:
            return {"error": f"Failed to load latest position: {e}", "symbol": symbol, "date": today_date}

        try:
            this_symbol_price = get_open_prices(today_date, [symbol], market=market)[f"{symbol}_price"]
        except KeyError:
            return {
                "error": f"Symbol {symbol} not found! This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
            }

        if this_symbol_price is None:
            return {
                "error": f"Price data not available for {symbol} at {today_date}.",
                "symbol": symbol,
                "date": today_date,
                "market": market,
            }

        try:
            cash_left = current_position["CASH"] - this_symbol_price * amount
        except Exception as e:
            return {
                "error": f"Failed to compute cash after purchase: {e}",
                "symbol": symbol,
                "date": today_date,
            }

        if cash_left < 0:
            return {
                "error": "Insufficient cash! This action will not be allowed.",
                "required_cash": this_symbol_price * amount,
                "cash_available": current_position.get("CASH", 0),
                "symbol": symbol,
                "date": today_date,
            }

        new_position = current_position.copy()
        new_position["CASH"] = cash_left
        new_position[symbol] = new_position.get(symbol, 0) + amount

        log_path = get_config_value("LOG_PATH", "./data/agent_data_twstock")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]
        position_file_path = os.path.join(
            project_root, "data", log_path, signature, "position", "position.jsonl"
        )
        with open(position_file_path, "a") as f:
            record = {
                "date": today_date,
                "id": current_action_id + 1,
                "this_action": {"action": "buy_tw", "symbol": symbol, "amount": amount},
                "positions": new_position,
            }
            print(f"Writing to position.jsonl: {json.dumps(record)}")
            f.write(json.dumps(record) + "\n")

        write_config_value("IF_TRADE", True)
        
    return new_position


@mcp.tool()
def sell_tw(symbol: str, amount: int) -> Dict[str, Any]:
    """
    Sell Taiwan stock function (台灣股票賣出)

    This function simulates Taiwan stock selling operations:
    1. Get current position and operation ID
    2. Get stock opening price for the day
    3. Validate sell conditions (position exists, sufficient quantity, lot size)
    4. Update position (decrease stock quantity, increase cash)
    5. Record transaction to position.jsonl file

    Taiwan stock trading rules:
    - Symbols must end with '.TW' (TWSE) or '.TWO' (TPEx)
    - Minimum lot size: 1000 shares (一張 = 1000股)
    - Amount must be a multiple of 1000
    - No T+1 restriction (can sell shares bought the same day)

    Args:
        symbol: Taiwan stock symbol ending with '.TW' or '.TWO', e.g. '2330.TW', '2454.TW'
        amount: Number of shares to sell; must be a positive multiple of 1000

    Returns:
        Dict[str, Any]:
          - Success: Updated position dictionary (stock quantities and CASH balance in TWD)
          - Failure: {"error": error message, ...}

    Example:
        >>> result = sell_tw("2330.TW", 1000)   # Sell 1 lot of TSMC
        >>> result = sell_tw("2454.TW", 2000)   # Sell 2 lots of MediaTek
    """
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    today_date = get_config_value("TODAY_DATE")
    market = "tw"

    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return {
            "error": f"Invalid amount format. Amount must be an integer. You provided: {amount}",
            "symbol": symbol,
            "date": today_date,
        }

    if amount <= 0:
        return {
            "error": f"Amount must be positive. You tried to sell {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
        }

    # Taiwan trading rule: 1 lot = 1000 shares
    if amount % 1000 != 0:
        return {
            "error": (
                f"Taiwan stocks must be traded in multiples of 1000 shares (1 lot = 1000 shares). "
                f"You tried to sell {amount} shares."
            ),
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
            "suggestion": (
                f"Please use {(amount // 1000) * 1000} or {((amount // 1000) + 1) * 1000} shares instead."
            ),
        }

    with _position_lock(signature):
        try:
            current_position, current_action_id = get_latest_position(today_date, signature)
        except Exception as e:
            return {"error": f"Failed to load latest position: {e}", "symbol": symbol, "date": today_date}

        try:
            this_symbol_price = get_open_prices(today_date, [symbol], market=market)[f"{symbol}_price"]
        except KeyError:
            return {
                "error": f"Symbol {symbol} not found! This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
            }

        if this_symbol_price is None:
            return {
                "error": f"Price data not available for {symbol} at {today_date}.",
                "symbol": symbol,
                "date": today_date,
            }

        if symbol not in current_position:
            return {
                "error": f"No position for {symbol}! This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
            }

        if current_position[symbol] < amount:
            return {
                "error": "Insufficient shares! This action will not be allowed.",
                "have": current_position.get(symbol, 0),
                "want_to_sell": amount,
                "symbol": symbol,
                "date": today_date,
            }

        new_position = current_position.copy()
        new_position[symbol] -= amount
        new_position["CASH"] = new_position.get("CASH", 0) + this_symbol_price * amount

        log_path = get_config_value("LOG_PATH", "./data/agent_data_twstock")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]
        position_file_path = os.path.join(
            project_root, "data", log_path, signature, "position", "position.jsonl"
        )
        with open(position_file_path, "a") as f:
            record = {
                "date": today_date,
                "id": current_action_id + 1,
                "this_action": {"action": "sell_tw", "symbol": symbol, "amount": amount},
                "positions": new_position,
            }
            print(f"Writing to position.jsonl: {json.dumps(record)}")
            f.write(json.dumps(record) + "\n")

        write_config_value("IF_TRADE", True)

    return new_position


if __name__ == "__main__":
    port = int(os.getenv("TW_TRADE_HTTP_PORT", "8006"))
    mcp.run(transport="streamable-http", port=port)
