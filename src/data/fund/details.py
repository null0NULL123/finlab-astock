"""
拉取场外基金的基础档案与深度信息（历史净值与持仓信息）。

由于涉及数千只基金，本脚本支持断点续传（如果中途断网，再次运行会跳过已下载的基金）。
"""

import argparse
import datetime
import os
import random
import sys
import time
from pathlib import Path

import akshare as ak
import pandas as pd


def download_basic(out_dir, funds):
    """拉取基金基础档案信息"""
    print(f"准备拉取 {len(funds)} 支基金档案信息...")
    count, fail = 0, 0

    for i, symbol in enumerate(funds):
        basic_file = out_dir / f"{symbol}_basic.csv"
        if basic_file.exists():
            continue

        print(f"[{i+1}/{len(funds)}] 获取 {symbol} 的档案...")
        try:
            df_basic = ak.fund_individual_basic_info_xq(symbol=symbol)
            if df_basic is not None and not df_basic.empty:
                df_basic.to_csv(basic_file, index=False)
        except Exception as e:
            print(f"  -> {symbol} basic 获取失败: {e}")
            fail += 1

        count += 1
        time.sleep(random.uniform(0.5, 2.0))

    print(f"档案信息拉取完毕。成功: {count}, 失败: {fail}")


def download_fees(out_dir, funds):
    """拉取基金费率信息"""
    print(f"准备拉取 {len(funds)} 支基金费率信息...")
    count, fail = 0, 0

    for i, symbol in enumerate(funds):
        detail_file = out_dir / f"{symbol}_fees.csv"
        if detail_file.exists():
            continue

        print(f"[{i+1}/{len(funds)}] 获取 {symbol} 的费率...")
        try:
            df_detail = ak.fund_individual_detail_info_xq(symbol=symbol)
            if df_detail is not None and not df_detail.empty:
                df_detail.to_csv(detail_file, index=False)
        except Exception as e:
            print(f"  -> {symbol} fees 获取失败: {e}")
            fail += 1

        count += 1
        time.sleep(random.uniform(0.5, 2.0))

    print(f"费率信息拉取完毕。成功: {count}, 失败: {fail}")


def download_nav(out_dir, funds):
    """拉取基金历史净值数据"""
    print(f"准备拉取 {len(funds)} 支基金历史净值...")
    count, fail = 0, 0

    for i, symbol in enumerate(funds):
        nav_file = out_dir / f"{symbol}_nav.csv"
        if nav_file.exists():
            continue

        print(f"[{i+1}/{len(funds)}] 获取 {symbol} 的历史净值...")
        try:
            df_nav = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
            if df_nav is not None and not df_nav.empty:
                df_nav.to_csv(nav_file, index=False)
        except Exception as e:
            print(f"  -> {symbol} 历史净值获取失败: {e}")
            fail += 1

        count += 1
        time.sleep(random.uniform(0.5, 2.0))

    print(f"历史净值拉取完毕。成功: {count}, 失败: {fail}")


def download_holdings(out_dir, funds):
    """拉取基金持仓数据"""
    print(f"准备拉取 {len(funds)} 支基金持仓数据...")
    count, fail = 0, 0

    for i, symbol in enumerate(funds):
        holdings_file = out_dir / f"{symbol}_holdings.csv"
        if holdings_file.exists():
            continue

        print(f"[{i+1}/{len(funds)}] 获取 {symbol} 的持仓...")
        try:
            df_hold = ak.fund_portfolio_hold_em(
                symbol=symbol, date=str(datetime.datetime.now().year)
            )
            if df_hold is not None and not df_hold.empty:
                df_hold.to_csv(holdings_file, index=False)
        except Exception as e:
            print(f"  -> {symbol} 持仓数据获取失败: {e}")
            fail += 1

        count += 1
        time.sleep(random.uniform(0.5, 2.0))

    print(f"持仓数据拉取完毕。成功: {count}, 失败: {fail}")


def main():
    parser = argparse.ArgumentParser(description="拉取场外基金的各类信息")
    parser.add_argument(
        "--src",
        type=str,
        default="output/fund/lists/public_funds_filtered_nobond_nofof_nofee.csv",
        help="输入的基金列表CSV文件名",
    )
    parser.add_argument("--basic", action="store_true", help="拉取基金档案信息")
    parser.add_argument("--fees", action="store_true", help="拉取基金费率信息")
    parser.add_argument("--nav", action="store_true", help="拉取基金历史净值信息")
    parser.add_argument("--holdings", action="store_true", help="拉取基金持仓信息")
    parser.add_argument(
        "--output", type=str, default="output/fund/details", help="输出目录"
    )

    args = parser.parse_args()

    if not (args.basic or args.fees or args.nav or args.holdings):
        print("未指定任何选项。请使用 --basic, --fees, --nav, --holdings，或同时使用多个选项。")
        parser.print_help()
        sys.exit(1)

    # 项目根目录（从 src/data/fund/ 向上4级）
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    csv_path = repo_root / args.src

    if not csv_path.exists():
        print(f"找不到输入的基金列表: {csv_path}")
        sys.exit(1)

    df_funds = pd.read_csv(csv_path)
    df_funds["基金代码"] = df_funds["基金代码"].astype(str).str.zfill(6)
    funds = df_funds["基金代码"].tolist()

    out_dir = repo_root / args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.basic:
        if not os.path.exists(out_dir / "basic"):
            os.makedirs(out_dir / "basic")
        download_basic(out_dir / "basic", funds)
    if args.fees:
        if not os.path.exists(out_dir / "fees"):
            os.makedirs(out_dir / "fees")
        download_fees(out_dir / "fees", funds)
    if args.nav:
        if not os.path.exists(out_dir / "nav"):
            os.makedirs(out_dir / "nav")
        download_nav(out_dir / "nav", funds)
    if args.holdings:
        if not os.path.exists(out_dir / "holdings"):
            os.makedirs(out_dir / "holdings")
        download_holdings(out_dir / "holdings", funds)


if __name__ == "__main__":
    main()
