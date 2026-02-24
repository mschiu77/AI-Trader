#!/bin/bash

# Taiwan stock data preparation

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT"

cd data/TW_stock

python get_daily_price_tw.py
python merge_jsonl_tw.py

cd ..
