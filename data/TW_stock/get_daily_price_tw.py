import os
import json
import datetime
import time
from collections import OrderedDict

import requests
from dotenv import load_dotenv

load_dotenv()

# Taiwan 50 index components (.TW suffix for TWSE stocks)
tw_50_codes = [
    "2330.TW",  # TSMC
    "2317.TW",  # Hon Hai / Foxconn
    "2454.TW",  # MediaTek
    "2308.TW",  # Delta Electronics
    "2881.TW",  # Fubon Financial
    "2882.TW",  # Cathay Financial
    "2412.TW",  # Chunghwa Telecom
    "1301.TW",  # Formosa Plastics
    "1303.TW",  # Nan Ya Plastics
    "2002.TW",  # China Steel
    "2886.TW",  # Mega Financial
    "2891.TW",  # CTBC Financial
    "2884.TW",  # E.SUN Financial
    "2303.TW",  # United Microelectronics (UMC)
    "3711.TW",  # ASE Technology
    "2382.TW",  # Quanta Computer
    "2357.TW",  # ASUS
    "2395.TW",  # Advantech
    "2408.TW",  # Innolux
    "2327.TW",  # Yageo
    "6505.TW",  # Formosa Petrochemical
    "1326.TW",  # Formosa Chemicals
    "1216.TW",  # Uni-President Enterprises
    "2207.TW",  # Hotai Motor
    "5880.TW",  # Chailease Holding
    "2603.TW",  # Evergreen Marine
    "2615.TW",  # Wan Hai Lines
    "2609.TW",  # Yang Ming Marine
    "2379.TW",  # Realtek Semiconductor
    "3034.TW",  # Novatek Microelectronics
    "2301.TW",  # Lite-On Technology
    "2353.TW",  # Acer
    "2324.TW",  # Compal Electronics
    "2376.TW",  # Gigabyte Technology
    "2345.TW",  # Accton Technology
    "3008.TW",  # Largan Precision
    "2388.TW",  # VIA Technologies
    "2049.TW",  # Hiwin Technologies
    "4904.TW",  # Far EasTone Telecom
    "2887.TW",  # Taishin Financial
]


def filter_data(data: dict, after_date: str):
    data_filtered = {}
    for date in data["Time Series (Daily)"]:
        date_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
        after_date_obj = datetime.datetime.strptime(after_date, "%Y-%m-%d")
        if date_obj > after_date_obj:
            data_filtered[date] = data["Time Series (Daily)"][date]
    data["Time Series (Daily)"] = data_filtered
    return data


def merge_data(existing_data: dict, new_data: dict):
    """Merge data: keep existing dates, only add new dates."""
    if existing_data is None or "Time Series (Daily)" not in existing_data:
        return new_data

    existing_dates = existing_data["Time Series (Daily)"]
    new_dates = new_data["Time Series (Daily)"]

    merged_dates = existing_dates.copy()
    for date in new_dates:
        if date not in merged_dates:
            merged_dates[date] = new_dates[date]

    sorted_dates = OrderedDict(sorted(merged_dates.items(), key=lambda x: x[0], reverse=True))

    merged_data = existing_data.copy()
    merged_data["Time Series (Daily)"] = sorted_dates

    if sorted_dates:
        merged_data["Meta Data"]["3. Last Refreshed"] = list(sorted_dates.keys())[0]

    return merged_data


def load_existing_data(filepath: str):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return None
    return None


def get_daily_price(symbol: str):
    # Use mis.twse.com.tw for real-time/daily snapshot data
    # Note: symbol format for TWSE is '2330.TW', but mis API expects 'tse_2330.tw'
    
    if symbol == "^TWII":
        twse_symbol = "tse_t00.tw"
    else:
        twse_symbol = f"tse_{symbol.lower()}"
        
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={twse_symbol}&json=1&delay=0"
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            print(f"Error fetching {symbol}: HTTP {r.status_code}")
            return
            
        data = r.json()
        msg_array = data.get("msgArray", [])
        
        if not msg_array:
            print(f"No data found for {symbol}")
            return
            
        stock_data = msg_array[0]
        
        # Extract data
        date_str = stock_data.get("d")  # YYYYMMDD
        if not date_str:
            print(f"Missing date for {symbol}")
            return
            
        date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        
        open_price = stock_data.get("o", "0.0000")
        high_price = stock_data.get("h", "0.0000")
        low_price = stock_data.get("l", "0.0000")
        close_price = stock_data.get("z", "0.0000") # 'z' is latest trade price
        volume = stock_data.get("v", "0") # Accumulated volume
        
        # If open/high/low/close are "-", treat as 0 or previous close (handle gracefully)
        if open_price == "-": open_price = close_price
        if high_price == "-": high_price = close_price
        if low_price == "-": low_price = close_price
        
        daily_data = {
            "1. open": open_price,
            "2. high": high_price,
            "3. low": low_price,
            "4. close": close_price,
            "5. volume": volume
        }
        
        print(f"Fetched {symbol} for date {date_formatted}")

        # Save to data/TW_stock/TW_stock_data to align with merge script
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "TW_stock_data")
        os.makedirs(data_dir, exist_ok=True)
        
        output_file = os.path.join(data_dir, f"daily_prices_{symbol}.json")
        existing_data = load_existing_data(output_file)
        
        # Initialize structure if new file
        if existing_data is None:
            existing_data = {
                "Meta Data": {
                    "1. Information": "Daily Prices (open, high, low, close) and Volumes",
                    "2. Symbol": symbol,
                    "3. Last Refreshed": date_formatted,
                    "4. Output Size": "Compact",
                    "5. Time Zone": "Asia/Taipei"
                },
                "Time Series (Daily)": {}
            }
        
        # Merge new data
        if "Time Series (Daily)" not in existing_data:
            existing_data["Time Series (Daily)"] = {}
            
        existing_data["Time Series (Daily)"][date_formatted] = daily_data
        
        # Sort dates descending
        sorted_dates = OrderedDict(sorted(existing_data["Time Series (Daily)"].items(), key=lambda x: x[0], reverse=True))
        existing_data["Time Series (Daily)"] = sorted_dates
        existing_data["Meta Data"]["3. Last Refreshed"] = list(sorted_dates.keys())[0] if sorted_dates else date_formatted

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)
            
    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        return

    # Respect rate limits slightly
    time.sleep(1)


if __name__ == "__main__":
    # Ensure data directory exists
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "TW_stock_data")
    os.makedirs(data_dir, exist_ok=True)
    
    for symbol in tw_50_codes:
        get_daily_price(symbol)
    # Also fetch Taiwan Weighted Index as benchmark
    get_daily_price("^TWII")
