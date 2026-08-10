"""Fetch company financial reports with AkShare and save to CSV files.

用法:
    python -m src.data.stock.financial_reports --codes 600519 000001
    python -m src.data.stock.financial_reports --codes SH600519 SZ000001 --out-dir output/stock/financial_reports
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import akshare as ak
import pandas as pd

from ...common.stock_utils import normalize_symbol

ReportFetcher = Callable[[str], pd.DataFrame]


def fetch_reports(symbol: str) -> dict[str, pd.DataFrame]:
    """Fetch three financial statements from Eastmoney endpoints in AkShare."""
    return {
        "balance_sheet": ak.stock_balance_sheet_by_report_em(symbol=symbol),
        "income_statement": ak.stock_profit_sheet_by_report_em(symbol=symbol),
        "cash_flow": ak.stock_cash_flow_sheet_by_report_em(symbol=symbol),
        "financial_abstract": ak.stock_financial_abstract(symbol=symbol[-6:]),
    }


def save_reports(symbol: str, reports: dict[str, pd.DataFrame], out_dir: Path) -> None:
    """Save each report to CSV in per-symbol folder."""
    symbol_dir = out_dir / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)

    for report_name, df in reports.items():
        out_path = symbol_dir / f"{report_name}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"[saved] {symbol} -> {out_path} rows={len(df)} cols={len(df.columns)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch company financial reports with AkShare"
    )
    parser.add_argument(
        "--codes",
        nargs="+",
        required=True,
        help="Stock codes, e.g. 600519 000001 or SH600519 SZ000001",
    )
    parser.add_argument(
        "--out-dir",
        default="output/stock/financial_reports",
        help="Directory to save CSV outputs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)

    ok = 0
    failed = 0

    for raw_code in args.codes:
        try:
            symbol = normalize_symbol(raw_code)
            print(f"[fetch] {raw_code} -> {symbol}")
            reports = fetch_reports(symbol)
            save_reports(symbol, reports, out_dir)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"[error] {raw_code}: {exc}", file=sys.stderr)

    print(f"[done] ok={ok}, failed={failed}, output={out_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


