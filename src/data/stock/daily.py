"""下载股票历史日线数据

支持两种数据源:
    1. baostock (默认, 无需网络代理, 免费)
    2. akshare (需直连东方财富 API)

用法:
    # 使用 baostock 下载 (推荐, 绕过代理)
    python -m src.data.stock.daily --codes 600519 000858 --start 20230101 --end 20260503
    python -m src.data.stock.daily --codes SH600519 --start 20240101

    # 使用 akshare 下载
    python -m src.data.stock.daily --codes 600519 --start 20230101 --end 20260503 --source akshare

    # 下载热门股票列表 (内置)
    python -m src.data.stock.daily --popular --start 20230101 --end 20260503

    # 从文件读取股票列表
    python -m src.data.stock.daily --list-file stock_list.txt --start 20230101 --end 20260503
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List

import pandas as pd

from ...common.stock_utils import normalize_symbol, symbol_to_baostock

# 内置热门股票列表 (覆盖主要行业板块)
POPULAR_STOCKS = [
    # 白酒
    "600519",  # 贵州茅台
    "000858",  # 五粮液
    "000568",  # 泸州老窖
    # 银行
    "600036",  # 招商银行
    "601318",  # 中国平安
    "601166",  # 兴业银行
    # 新能源
    "300750",  # 宁德时代
    "002594",  # 比亚迪
    "601012",  # 隆基绿能
    # 科技/半导体
    "002415",  # 海康威视
    "603986",  # 兆易创新
    "002230",  # 科大讯飞
    # 医药
    "600276",  # 恒瑞医药
    "300760",  # 迈瑞医疗
    "000538",  # 云南白药
    # 消费
    "000333",  # 美的集团
    "600887",  # 伊利股份
    "002714",  # 牧原股份
    # 基建/地产
    "600048",  # 保利发展
    "601668",  # 中国建筑
    # 证券
    "600030",  # 中信证券
    "601688",  # 华泰证券
    # 电力
    "600900",  # 长江电力
    "601985",  # 中国核电
    # 通信
    "600941",  # 中国移动
    "000063",  # 中兴通讯
]


def fetch_stock_daily_baostock(code: str, start: str, end: str) -> pd.DataFrame:
    """使用 baostock 获取股票日线数据 (不复权)

    Args:
        code: 股票代码 (如 600519 或 SH600519)
        start: 开始日期 YYYYMMDD
        end: 结束日期 YYYYMMDD

    Returns:
        DataFrame with columns: 日期,开盘,收盘,最高,最低,成交量,成交额,symbol
    """
    import baostock as bs

    symbol = normalize_symbol(code)
    bs_code = symbol_to_baostock(symbol)

    # 格式化日期
    start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"

    lg = bs.login()
    if lg.error_code != "0":
        raise ConnectionError(f"Baostock login failed: {lg.error_msg}")

    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date=start_fmt,
            end_date=end_fmt,
            frequency="d",
            adjustflag="3",  # 不复权
        )

        if rs.error_code != "0":
            raise ValueError(f"Query failed: {rs.error_msg}")

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            return pd.DataFrame()

        df = pd.DataFrame(
            data_list,
            columns=["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"],
        )

        # 转换数据类型
        for col in ["开盘", "收盘", "最高", "最低", "成交量", "成交额"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # 去除无效数据行 (volume=0 通常是停牌日)
        df = df[df["成交量"] > 0].reset_index(drop=True)

        df["symbol"] = symbol
        return df

    finally:
        bs.logout()


def fetch_stock_daily_akshare(code: str, start: str, end: str) -> pd.DataFrame:
    """使用 akshare 获取股票日线数据 (不复权)"""
    import akshare as ak

    symbol = normalize_symbol(code)
    raw_symbol = symbol[-6:]

    df = ak.stock_zh_a_hist(
        symbol=raw_symbol,
        period="daily",
        start_date=start,
        end_date=end,
        adjust="",  # 不复权
    )

    if df.empty:
        return df

    df["symbol"] = symbol
    return df


def fetch_stock_daily(
    code: str, start: str, end: str, source: str = "baostock"
) -> pd.DataFrame:
    """获取单只股票的历史日线数据"""
    if source == "baostock":
        return fetch_stock_daily_baostock(code, start, end)
    elif source == "akshare":
        return fetch_stock_daily_akshare(code, start, end)
    else:
        raise ValueError(f"unknown source: {source}")


def load_stock_list_file(filepath: str) -> List[str]:
    """从文件加载股票列表 (每行一个代码, #开头为注释)"""
    codes = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                codes.append(line)
    return codes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下载股票历史日线数据")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--codes",
        nargs="+",
        help="股票代码列表, 如 600519 000858 或 SH600519 SZ000858",
    )
    group.add_argument(
        "--popular",
        action="store_true",
        help="下载内置热门股票列表 (26只)",
    )
    group.add_argument(
        "--list-file",
        help="从文件读取股票列表 (每行一个代码)",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="开始日期, 格式 YYYYMMDD, 如 20230101",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="结束日期, 格式 YYYYMMDD, 如 20260503",
    )
    parser.add_argument(
        "--source",
        default="baostock",
        choices=["baostock", "akshare"],
        help="数据源: baostock (默认, 推荐) 或 akshare",
    )
    parser.add_argument(
        "--out-dir",
        default="output/stock/details/daily",
        help="日线数据输出目录",
    )
    parser.add_argument(
        "--delay", type=float, default=0.3, help="请求间隔秒数, 默认 0.3"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载已存在的文件",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 确定股票列表
    if args.popular:
        codes = POPULAR_STOCKS
        print(f"[info] 使用内置热门股票列表: {len(codes)} 只")
    elif args.list_file:
        codes = load_stock_list_file(args.list_file)
        print(f"[info] 从文件加载: {args.list_file} -> {len(codes)} 只")
    else:
        codes = list(args.codes)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 如果使用 baostock, 清除代理环境变量
    if args.source == "baostock":
        for k in [
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "ALL_PROXY",
            "all_proxy",
        ]:
            os.environ.pop(k, None)

    ok = 0
    failed = 0
    skipped = 0

    for i, raw_code in enumerate(codes):
        try:
            symbol = normalize_symbol(raw_code)
            out_path = out_dir / f"{symbol}_daily.csv"

            if out_path.exists() and not args.force:
                print(f"[skip] ({i + 1}/{len(codes)}) {symbol} 已存在")
                skipped += 1
                continue

            print(f"[fetch] ({i + 1}/{len(codes)}) {symbol} ...", end=" ", flush=True)
            df = fetch_stock_daily(raw_code, args.start, args.end, args.source)

            if df.empty:
                print(f"无数据")
                failed += 1
                continue

            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            date_range = f"{df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}"
            print(f"OK, {len(df)} 行 ({date_range})")
            ok += 1

            if i < len(codes) - 1:
                time.sleep(args.delay)

        except Exception as exc:
            failed += 1
            print(f"ERROR: {exc}", file=sys.stderr)

    print(f"\n[done] 成功={ok}, 跳过={skipped}, 失败={failed}, 输出目录={out_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


