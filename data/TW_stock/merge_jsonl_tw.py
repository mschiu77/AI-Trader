import glob
import json
import os
from collections import OrderedDict
from pathlib import Path

tw_50_codes = [
    "2330.TW",
    "2317.TW",
    "2454.TW",
    "2308.TW",
    "2881.TW",
    "2882.TW",
    "2412.TW",
    "1301.TW",
    "1303.TW",
    "2002.TW",
    "2886.TW",
    "2891.TW",
    "2884.TW",
    "2303.TW",
    "3711.TW",
    "2382.TW",
    "2357.TW",
    "2395.TW",
    "2408.TW",
    "2327.TW",
    "6505.TW",
    "1326.TW",
    "1216.TW",
    "2207.TW",
    "5880.TW",
    "2603.TW",
    "2615.TW",
    "2609.TW",
    "2379.TW",
    "3034.TW",
    "2301.TW",
    "2353.TW",
    "2324.TW",
    "2376.TW",
    "2345.TW",
    "3008.TW",
    "2388.TW",
    "2049.TW",
    "4904.TW",
    "2887.TW",
]

# Stock name mapping for Taiwan 50
tw_stock_names = {
    "2330.TW": "台積電",
    "2317.TW": "鴻海",
    "2454.TW": "聯發科",
    "2308.TW": "台達電",
    "2881.TW": "富邦金",
    "2882.TW": "國泰金",
    "2412.TW": "中華電",
    "1301.TW": "台塑",
    "1303.TW": "南亞",
    "2002.TW": "中鋼",
    "2886.TW": "兆豐金",
    "2891.TW": "中信金",
    "2884.TW": "玉山金",
    "2303.TW": "聯電",
    "3711.TW": "日月光投控",
    "2382.TW": "廣達",
    "2357.TW": "華碩",
    "2395.TW": "研華",
    "2408.TW": "奇美電",
    "2327.TW": "國巨",
    "6505.TW": "台塑化",
    "1326.TW": "台化",
    "1216.TW": "統一",
    "2207.TW": "和泰車",
    "5880.TW": "合庫金",
    "2603.TW": "長榮",
    "2615.TW": "萬海",
    "2609.TW": "陽明",
    "2379.TW": "瑞昱",
    "3034.TW": "聯詠",
    "2301.TW": "光寶科",
    "2353.TW": "宏碁",
    "2324.TW": "仁寶",
    "2376.TW": "技嘉",
    "2345.TW": "智邦",
    "3008.TW": "大立光",
    "2388.TW": "威盛",
    "2049.TW": "上銀",
    "4904.TW": "遠傳",
    "2887.TW": "台新金",
}

current_dir = os.path.dirname(os.path.abspath(__file__))
pattern = os.path.join(current_dir, "TW_stock_data/daily_prices_*.json")
files = sorted(glob.glob(pattern))

output_file = os.path.join(current_dir, "merged.jsonl")

processed_count = 0
skipped_count = 0

with open(output_file, "w", encoding="utf-8") as fout:
    for fp in files:
        basename = os.path.basename(fp)
        # Only include files matching known TW symbols
        matched_symbol = None
        for symbol in tw_50_codes:
            if symbol in basename:
                matched_symbol = symbol
                break
        if matched_symbol is None:
            skipped_count += 1
            continue

        with open(fp, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"  ⚠️  {basename} - JSON decode error: {e}")
                skipped_count += 1
                continue

        try:
            series = None
            for key, value in data.items():
                if key.startswith("Time Series"):
                    series = value
                    break

            if isinstance(series, dict) and series:
                # Rename open/close keys
                for d, bar in list(series.items()):
                    if not isinstance(bar, dict):
                        continue
                    if "1. open" in bar:
                        bar["1. buy price"] = bar.pop("1. open")
                    if "4. close" in bar:
                        bar["4. sell price"] = bar.pop("4. close")

                # For the latest date, only keep buy price (today's open, hide future data)
                latest_date = max(series.keys())
                latest_bar = series.get(latest_date, {})
                if isinstance(latest_bar, dict):
                    buy_val = latest_bar.get("1. buy price")
                    series[latest_date] = {"1. buy price": buy_val} if buy_val is not None else {}

                # Update Meta Data
                meta = data.get("Meta Data", {})
                if isinstance(meta, dict):
                    meta["1. Information"] = "Daily Prices (buy price, high, low, sell price) and Volumes"
                    symbol = meta.get("2. Symbol", matched_symbol)
                    # Normalize: Alpha Vantage may return symbol with exchange suffix
                    if not symbol.endswith(".TW"):
                        symbol = matched_symbol
                    meta["2. Symbol"] = symbol
                    stock_name = tw_stock_names.get(symbol, "")
                    if stock_name:
                        meta["2.1. Name"] = stock_name
                    meta["5. Time Zone"] = "Asia/Taipei"

                processed_count += 1
        except Exception as e:
            print(f"  ⚠️  {basename} - processing error: {e}")

        fout.write(json.dumps(data, ensure_ascii=False) + "\n")

print(f"✅ Merge complete!")
print(f"📊 Statistics:")
print(f"   - Processed: {processed_count} files")
print(f"   - Skipped:   {skipped_count} files")
print(f"   - Output:    {output_file}")
