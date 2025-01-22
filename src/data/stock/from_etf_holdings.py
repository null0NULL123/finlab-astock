"""基于 ETF 持仓获取股票相关信息并同步到 output/stock/ 目录

功能：
1. 读取 ETF 列表
2. 获取指定 ETF 的持仓数据（前N大重仓股）
3. 提取持仓中的股票代码
4. 自动下载这些股票的基本信息 -> output/stock/details/basic/
5. 自动下载这些股票的历史日线数据(不复权) -> output/stock/details/daily/
6. 整合持仓+基本信息输出为汇总 CSV

用法：
    python -m src.data.stock.from_etf_holdings --etf-code 510300 --top-n 10
    python -m src.data.stock.from_etf_holdings --etf-code 159915 --top-n 20 --start 20250101 --end 20260503
"""

import argparse
import datetime
import re
import sys
import time
from pathlib import Path

import akshare as ak
import pandas as pd

from ...common.stock_utils import normalize_symbol


def get_etf_holdings(etf_code: str, year: str = None) -> pd.DataFrame:
    if year is None:
        year = str(datetime.datetime.now().year)
    symbol = re.sub(r"\D", "", str(etf_code)).zfill(6)
    try:
        df = ak.fund_portfolio_hold_em(symbol=symbol, date=year)
        return df
    except Exception as e:
        print(f"获取 ETF {etf_code} 持仓数据失败: {e}")
        return pd.DataFrame()


def extract_stock_codes_from_holdings(df: pd.DataFrame, top_n: int = 10) -> list:
    if df.empty or "股票代码" not in df.columns:
        print("持仓数据中未找到 '股票代码' 列，可用列名: %s" % list(df.columns))
        return []
    codes = df["股票代码"].astype(str).unique().tolist()[:top_n]
    return codes


def download_basic_info(stock_codes: list, basic_dir: Path, delay: float) -> None:
    basic_dir.mkdir(parents=True, exist_ok=True)
    for code in stock_codes:
        try:
            symbol = normalize_symbol(code)
            out_path = basic_dir / f"{symbol}_basic.csv"
            if out_path.exists():
                continue
            df = ak.stock_individual_info_em(symbol=symbol[-6:])
            if not df.empty:
                info = dict(zip(df["item"], df["value"]))
                info["symbol"] = symbol
                pd.DataFrame([info]).to_csv(out_path, index=False, encoding="utf-8-sig")
            time.sleep(delay)
        except Exception as e:
            print(f"  [error] 基本信息 {code}: {e}")


def download_daily_data(
    stock_codes: list, daily_dir: Path, start: str, end: str, delay: float
) -> None:
    daily_dir.mkdir(parents=True, exist_ok=True)
    for code in stock_codes:
        try:
            symbol = normalize_symbol(code)
            out_path = daily_dir / f"{symbol}_daily.csv"
            if out_path.exists():
                continue
            df = ak.stock_zh_a_hist(
                symbol=symbol[-6:],
                period="daily",
                start_date=start,
                end_date=end,
                adjust="",
            )
            if not df.empty:
                df["symbol"] = symbol
                df.to_csv(out_path, index=False, encoding="utf-8-sig")
            time.sleep(delay)
        except Exception as e:
            print(f"  [error] 日线数据 {code}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="基于 ETF 持仓获取股票并同步到 output/stock/"
    )
    parser.add_argument(
        "--etf-code",
        type=str,
        default="510300",
        help="ETF 代码，如 510300 (沪深300ETF)",
    )
    parser.add_argument(
        "--top-n", type=int, default=10, help="取前 N 大重仓股，默认 10"
    )
    parser.add_argument(
        "--year",
        type=str,
        default=str(datetime.datetime.now().year),
        help="持仓数据年份",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/stock/etf_holdings_analysis.csv",
        help="汇总输出文件路径",
    )
    parser.add_argument(
        "--start", type=str, default="20250101", help="日线数据开始日期, 默认 20250101"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=datetime.datetime.now().strftime("%Y%m%d"),
        help="日线数据结束日期",
    )
    parser.add_argument("--delay", type=float, default=0.3, help="请求间隔秒数")
    parser.add_argument("--skip-daily", action="store_true", help="跳过日线数据下载")
    parser.add_argument("--skip-basic", action="store_true", help="跳过基本信息下载")

    args = parser.parse_args()

    basic_dir = Path("output/stock/details/basic")
    daily_dir = Path("output/stock/details/daily")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== ETF 持仓 -> 股票数据同步 ===")
    print(f"  ETF: {args.etf_code}  重仓股数量: {args.top_n}  年份: {args.year}")
    print(f"  日线日期: {args.start} ~ {args.end}")
    print(f"  输出: {output_path}")

    # Step 1: 获取 ETF 持仓
    print(f"\n1. 获取 ETF {args.etf_code} 持仓数据...")
    df_holdings = get_etf_holdings(args.etf_code, args.year)
    if df_holdings.empty:
        print("获取持仓数据失败，退出。")
        sys.exit(1)
    print(f"   持仓记录: {len(df_holdings)}")
    print(df_holdings.head())

    # Step 2: 提取股票代码
    stock_codes = extract_stock_codes_from_holdings(df_holdings, top_n=args.top_n)
    print(f"\n2. 重仓股代码 ({len(stock_codes)}): {stock_codes}")
    if not stock_codes:
        print("未提取到股票代码，退出。")
        sys.exit(1)

    # Step 3: 下载基本信息
    if not args.skip_basic:
        print(f"\n3. 下载基本信息 -> {basic_dir}")
        download_basic_info(stock_codes, basic_dir, args.delay)
    else:
        print(f"\n3. (跳过) 基本信息")

    # Step 4: 下载日线数据
    if not args.skip_daily:
        print(f"\n4. 下载日线数据(不复权) -> {daily_dir}")
        download_daily_data(stock_codes, daily_dir, args.start, args.end, args.delay)
    else:
        print(f"\n4. (跳过) 日线数据")

    # Step 5: 合并持仓+基本信息汇总
    print(f"\n5. 汇总输出 -> {output_path}")
    all_info = []
    for code in stock_codes:
        try:
            df = ak.stock_individual_info_em(symbol=code)
            if not df.empty:
                info = dict(zip(df["item"], df["value"]))
                info["股票代码"] = code
                all_info.append(info)
        except Exception:
            pass

    if all_info:
        df_info = pd.DataFrame(all_info)
        holdings_subset = df_holdings[
            df_holdings["股票代码"].astype(str).isin(stock_codes)
        ][["股票代码", "股票名称", "占净值比例", "持股数", "持仓市值"]].copy()
        holdings_subset["股票代码"] = holdings_subset["股票代码"].astype(str)
        df_info["股票代码"] = df_info["股票代码"].astype(str)
        df_merged = pd.merge(df_info, holdings_subset, on="股票代码", how="left")
        df_merged.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(df_merged.to_string())
    else:
        print("无汇总数据可输出")

    print(f"\n输出目录结构:")
    print(f"  output/stock/")
    print(f"    details/basic/   - 股票基本信息 (per-stock)")
    print(f"    details/daily/   - 历史日线数据 不复权 (per-stock)")
    print(f"    {output_path.name}  - 持仓+基本信息汇总")
    print(f"    financial_reports/  - 财报数据 (per-stock, 已有)")


if __name__ == "__main__":
    main()

# Updated: 2025-01-22
