"""下载股票基本信息 (A股 实时概况)

用法:
    python -m src.data.stock.basic_info --codes 600519 000858
    python -m src.data.stock.basic_info --all  # 下载全市场股票
    python -m src.data.stock.basic_info --codes SH600519 SZ000858 --out-dir output/stock/details/basic
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import akshare as ak
import pandas as pd

from ...common.stock_utils import normalize_symbol


def fetch_stock_basic_info(stock_code: str) -> pd.DataFrame:
    """获取单只股票的基本信息"""
    symbol = normalize_symbol(stock_code)
    raw_symbol = symbol[-6:]

    df = ak.stock_individual_info_em(symbol=raw_symbol)
    if df.empty:
        return df

    info = dict(zip(df["item"], df["value"]))
    info["symbol"] = symbol
    return pd.DataFrame([info])


def fetch_all_stocks_list() -> pd.DataFrame:
    """获取全市场 A 股实时行情列表 (含代码、名称、最新价等)"""
    return ak.stock_zh_a_spot_em()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下载股票基本信息")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--codes", nargs="+", help="股票代码列表, 如 600519 000858 或 SH600519 SZ000858"
    )
    group.add_argument(
        "--all", action="store_true", help="下载全市场 A 股股票列表并逐只获取基本信息"
    )
    parser.add_argument(
        "--out-dir",
        default="output/stock/details/basic",
        help="基本信息输出目录",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5, help="请求间隔秒数, 默认 0.5"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    codes: list[str] = []

    if args.all:
        print("[fetch] 正在获取全市场 A 股列表...")
        df_list = fetch_all_stocks_list()
        codes = df_list["代码"].astype(str).tolist()
        print(f"[fetch] 获取到 {len(codes)} 只股票")

        # 同时保存股票列表到 lists 目录
        lists_dir = Path("output/stock/lists")
        lists_dir.mkdir(parents=True, exist_ok=True)
        list_path = lists_dir / "all_a_stocks_akshare.csv"
        df_list.to_csv(list_path, index=False, encoding="utf-8-sig")
        print(f"[saved] 股票列表 -> {list_path}")
    else:
        codes = list(args.codes)

    ok = 0
    failed = 0

    for raw_code in codes:
        try:
            symbol = normalize_symbol(raw_code)
            out_path = out_dir / f"{symbol}_basic.csv"

            if out_path.exists():
                ok += 1
                continue

            df = fetch_stock_basic_info(raw_code)
            if df.empty:
                print(f"[warn] {symbol} 无数据")
                failed += 1
                continue

            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"[saved] {symbol} -> {out_path}")
            ok += 1
            time.sleep(args.delay)

        except Exception as exc:
            failed += 1
            print(f"[error] {raw_code}: {exc}", file=sys.stderr)

    print(f"[done] ok={ok}, failed={failed}, output={out_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
