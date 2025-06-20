"""Download ETF daily data from Tencent Finance API.

Usage:
    python -m src.data.etf.daily_tencent --popular --start 20230101 --end 20260503
    python -m src.data.etf.daily_tencent --codes 510300 159919 --start 20230101 --end 20260503
    python -m src.data.etf.daily_tencent --list-file etf_list.txt --start 20230101 --end 20260503
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pandas as pd

POPULAR_ETFS = [
    "510300",
    "510050",
    "510500",
    "512100",
    "159919",
    "159915",
    "159922",  # Broad-based
    "512010",
    "512880",
    "515790",
    "516160",
    "512690",
    "515030",
    "512480",  # Industry
    "512660",
    "159869",
    "512800",
    "515210",
    "159825",
    "512200",
    "513100",
    "513050",
    "159941",
    "513500",  # Cross-border
    "511010",
    "518880",  # Bond / Commodity
]


def normalize_code(code: str) -> str:
    """Strip market prefix and zero-pad to 6 digits."""
    for p in ("sh", "sz", "SH", "SZ"):
        code = code.removeprefix(p)
    return code.zfill(6)


def market_prefix(code: str) -> str:
    """Determine market prefix from ETF code."""
    return "sh" if code.startswith(("5", "6")) else "sz"


def fetch_chunk(symbol: str, start: str, end: str, env: dict) -> list:
    """Fetch a single date-range chunk from the Tencent Finance API."""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,{start},{end},1000,qfq"
    r = subprocess.run(
        ["curl", "-s", "--max-time", "15", url],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    if r.returncode != 0:
        raise ValueError(f"curl failed: {r.stderr}")
    data = json.loads(r.stdout)
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('msg')}")
    raw = data.get("data", {})
    if isinstance(raw, list):
        return []
    stock = raw.get(symbol, {})
    if not isinstance(stock, dict):
        return []
    for key in ("qfqday", "day", "qfqweek", "week"):
        if key in stock:
            return stock[key]
    return []


def fetch_etf_daily(code: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV data for an ETF over a date range.

    Splits the range into ~5-month chunks to stay within API limits.

    Args:
        code: 6-digit ETF code.
        start: Start date as YYYYMMDD.
        end: End date as YYYYMMDD.

    Returns:
        DataFrame with columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, symbol.
    """
    code = normalize_code(code)
    symbol = f"{market_prefix(code)}{code}"

    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().endswith("PROXY") and not k.upper().startswith("ALL_PROXY")
    }

    start_dt, end_dt = (
        datetime.strptime(start, "%Y%m%d"),
        datetime.strptime(end, "%Y%m%d"),
    )
    all_klines, chunk_start = [], start_dt

    while chunk_start <= end_dt:
        m = chunk_start.month + 5
        y = chunk_start.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        try:
            chunk_end = chunk_start.replace(year=y, month=m, day=1) - timedelta(days=1)
        except ValueError:
            chunk_end = chunk_start.replace(year=y, month=m, day=28)
        chunk_end = min(chunk_end, end_dt)

        try:
            klines = fetch_chunk(
                symbol,
                chunk_start.strftime("%Y-%m-%d"),
                chunk_end.strftime("%Y-%m-%d"),
                env,
            )
            if klines:
                all_klines.extend(klines)
        except Exception:
            pass

        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(0.3)

    if not all_klines:
        return pd.DataFrame()

    seen, records = set(), []
    for row in all_klines:
        if len(row) >= 6 and row[0] not in seen:
            seen.add(row[0])
            records.append(
                {
                    "日期": row[0],
                    "开盘": float(row[1]),
                    "收盘": float(row[2]),
                    "最高": float(row[3]),
                    "最低": float(row[4]),
                    "成交量": float(row[5]),
                    "成交额": 0.0,
                }
            )
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).sort_values("日期").reset_index(drop=True)
    df["symbol"] = f"{market_prefix(code).upper()}{code}"
    return df


def load_etf_list_file(filepath: str) -> List[str]:
    """Load ETF codes from a text file (one per line, # for comments)."""
    with open(filepath, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ETF daily data from Tencent Finance API")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--codes", nargs="+", help="ETF code list")
    group.add_argument("--popular", action="store_true", help="Use built-in popular ETF list")
    group.add_argument("--list-file", help="Read ETF codes from a file")
    parser.add_argument("--start", required=True, help="Start date YYYYMMDD")
    parser.add_argument("--end", required=True, help="End date YYYYMMDD")
    parser.add_argument("--out-dir", default="output/etf/details/daily")
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    codes = (
        POPULAR_ETFS
        if args.popular
        else (
            load_etf_list_file(args.list_file) if args.list_file else list(args.codes)
        )
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = failed = skipped = 0
    for i, raw_code in enumerate(codes):
        try:
            code = normalize_code(raw_code)
            symbol = f"{market_prefix(code).upper()}{code}"
            out_path = out_dir / f"{symbol}_daily.csv"

            if out_path.exists() and not args.force:
                print(f"[skip] ({i + 1}/{len(codes)}) {symbol} exists")
                skipped += 1
                continue

            print(f"[fetch] ({i + 1}/{len(codes)}) {symbol} ...", end=" ", flush=True)
            df = fetch_etf_daily(code, args.start, args.end)
            if df.empty:
                print("no data")
                failed += 1
                continue

            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"OK, {len(df)} rows ({df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]})")
            ok += 1
            if i < len(codes) - 1:
                time.sleep(args.delay)
        except Exception as exc:
            failed += 1
            print(f"ERROR: {exc}", file=sys.stderr)

    print(f"\n[done] success={ok}, skipped={skipped}, failed={failed}, output={out_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

# Updated: 2025-04-09

# Updated: 2025-06-20
