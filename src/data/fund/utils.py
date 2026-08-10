"""
基金工具函数

提供基金数据下载、处理的通用工具：
- normalize_fund_code: 规范化基金代码为6位数字
- load_fund_list: 从CSV加载基金代码列表
- download_with_retry: 带断点续传和重试的通用下载器
- print_stats: 打印下载统计信息
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from tqdm import tqdm

logger = logging.getLogger(__name__)

# 项目根目录（从 src/data/fund/ 向上4级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FUND_OUTPUT_DIR = PROJECT_ROOT / "output" / "fund"


def setup_logging(level=logging.INFO):
    """统一的日志配置"""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def normalize_fund_code(code: str) -> str:
    """规范化基金代码为6位数字

    Args:
        code: 基金代码

    Returns:
        6位数字代码
    """
    code = str(code).strip()
    symbol = re.sub(r"\D", "", code)
    return symbol.zfill(6)


def load_fund_list(fund_list_path: str, code_column: str = "基金代码") -> list:
    """加载基金列表文件

    Args:
        fund_list_path: 基金列表 CSV 文件路径
        code_column: 代码列名

    Returns:
        基金代码列表
    """
    if not os.path.exists(fund_list_path):
        logger.error(f"基金列表文件不存在: {fund_list_path}")
        return []

    df = pd.read_csv(fund_list_path)

    # 尝试多种可能的列名
    if code_column not in df.columns:
        for col in ["代码", "fund_code", "symbol"]:
            if col in df.columns:
                code_column = col
                break

    df[code_column] = df[code_column].astype(str).apply(normalize_fund_code)
    return df[code_column].tolist()


def download_with_retry(
    items: list,
    download_func: Callable,
    output_dir: str,
    file_suffix: str,
    get_id_func: Callable = lambda x: x,
    sleep_range: tuple = (0.5, 2.0),
    desc: str = "下载中",
    skip_existing: bool = True,
) -> dict:
    """通用的下载函数，支持断点续传和重试

    Args:
        items: 要下载的项目列表
        download_func: 下载函数，接受单个项目作为参数，返回 DataFrame
        output_dir: 输出目录
        file_suffix: 文件后缀（如 '_nav.csv'）
        get_id_func: 从项目中提取 ID 的函数
        sleep_range: 睡眠时间范围
        desc: 进度条描述
        skip_existing: 是否跳过已存在的文件

    Returns:
        包含 success, fail, skip 计数的字典
    """
    os.makedirs(output_dir, exist_ok=True)

    stats = {"success": 0, "fail": 0, "skip": 0}

    for item in tqdm(items, desc=desc):
        item_id = get_id_func(item)
        output_file = os.path.join(output_dir, f"{item_id}{file_suffix}")

        # 断点续传：已存在则跳过
        if skip_existing and os.path.exists(output_file):
            stats["skip"] += 1
            continue

        try:
            df = download_func(item)
            if df is not None and not df.empty:
                df.to_csv(output_file, index=False, encoding="utf-8-sig")
                stats["success"] += 1
            else:
                logger.warning(f"[{item_id}] 返回空数据，已跳过。")
                stats["fail"] += 1
        except Exception as e:
            logger.error(f"[{item_id}] 获取失败: {e}")
            stats["fail"] += 1

        # 随机延迟，避免请求过于频繁
        if isinstance(sleep_range, tuple):
            time.sleep(random.uniform(*sleep_range))
        else:
            time.sleep(sleep_range)

    return stats


def print_stats(stats: dict, desc: str = "下载"):
    """打印下载统计信息

    Args:
        stats: 统计字典
        desc: 描述文本
    """
    logger.info(
        f"{desc}完成！成功: {stats['success']}, "
        f"跳过: {stats['skip']}, "
        f"失败/无数据: {stats['fail']}"
    )

