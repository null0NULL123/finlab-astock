"""
下载场外公募基金的历史净值数据（日K线）。

支持断点续传，已下载的基金会自动跳过。
"""

import argparse
import datetime
import logging
import os
import time

import akshare as ak
import pandas as pd
from tqdm import tqdm

from .utils import setup_logging

setup_logging()


def download_fund_nav(
    fund_list_path: str,
    output_dir: str,
    start_date: str,
    end_date: str,
    sleep: float,
    limit: int = 0,
):
    """批量下载基金历史净值数据

    Args:
        fund_list_path: 基金列表CSV文件路径
        output_dir: 输出目录
        start_date: 开始日期，格式 YYYYMMDD
        end_date: 结束日期，格式 YYYYMMDD
        sleep: 每次请求间隔秒数
        limit: 限制下载数量，0表示全部
    """
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(fund_list_path):
        logging.error(
            f"基金列表文件不存在: {fund_list_path}。请先运行 fetch_all_public_funds_akshare.py 获取列表。"
        )
        return

    df_fund = pd.read_csv(fund_list_path)
    logging.info(f"成功读取 {len(df_fund)} 个基金代码。准备下载历史净值...")

    # 应用限制
    if limit > 0:
        df_fund = df_fund.head(limit)
        logging.info(f"限制下载数量为: {limit}")

    success_count = 0
    fail_count = 0
    skip_count = 0

    for _, row in tqdm(
        df_fund.iterrows(), total=len(df_fund), desc="正在获取基金历史净值"
    ):
        # 获取基金代码，支持多种列名
        fund_code = str(row.get("基金代码", row.get("代码", ""))).strip()
        fund_name = str(row.get("基金名称", row.get("名称", ""))).strip()

        # 规范化基金代码为6位
        fund_code = fund_code.zfill(6)

        if not fund_code or fund_code == "000000":
            logging.warning(f"无效的基金代码: {fund_code}")
            fail_count += 1
            continue

        output_file = os.path.join(output_dir, f"{fund_code}_nav.csv")

        # 断点续传：已存在则跳过
        if os.path.exists(output_file):
            skip_count += 1
            continue

        try:
            # 获取基金历史净值数据
            df_nav = ak.fund_open_fund_info_em(
                symbol=fund_code, indicator="单位净值走势"
            )

            if df_nav is not None and not df_nav.empty:
                # 增加基金代码和名称列方便识别
                df_nav.insert(0, "基金代码", fund_code)
                df_nav.insert(1, "基金名称", fund_name)
                df_nav.to_csv(output_file, index=False, encoding="utf-8-sig")
                success_count += 1
            else:
                logging.warning(f"[{fund_code}] {fund_name} 返回空数据，已跳过。")
                fail_count += 1
        except Exception as e:
            logging.error(f"[{fund_code}] {fund_name} 获取失败: {e}")
            fail_count += 1

        time.sleep(sleep)

    logging.info(
        f"下载任务完成！成功: {success_count}, 跳过: {skip_count}, 失败/无数据: {fail_count}。"
        f"数据保存在 {output_dir} 目录下。"
    )


def main():
    parser = argparse.ArgumentParser(description="下载场外公募基金历史净值数据")
    parser.add_argument(
        "--fund-list",
        type=str,
        default="output/funds/all_public_funds_akshare.csv",
        help="基金列表CSV路径",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/fund/details/nav",
        help="输出目录",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="",
        help="开始日期，格式 YYYYMMDD，默认3年前",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="",
        help="结束日期，格式 YYYYMMDD，默认今天",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="每次请求间隔秒数，默认0.5",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="限制下载数量，0表示全部，默认0",
    )
    args = parser.parse_args()

    # 默认日期范围：3年前到今天
    today = datetime.date.today()
    if not args.end_date:
        args.end_date = today.strftime("%Y%m%d")
    if not args.start_date:
        three_years_ago = today.replace(year=today.year - 3)
        args.start_date = three_years_ago.strftime("%Y%m%d")

    logging.info(f"日期范围: {args.start_date} ~ {args.end_date}")

    download_fund_nav(
        fund_list_path=args.fund_list,
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        sleep=args.sleep,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()

# Updated: 2025-01-03

# Updated: 2025-09-11
