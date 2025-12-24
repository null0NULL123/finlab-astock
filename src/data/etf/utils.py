"""ETF utility functions.

Provides common helpers for ETF code normalization, market prefix detection,
ETF list loading, batch downloading, and column name matching.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from tqdm import tqdm

logger = logging.getLogger(__name__)


def normalize_etf_code(code: str) -> str:
    """Normalize an ETF code to a 6-digit string.

    Args:
        code: ETF code, possibly with sh/sz prefix or other non-digit chars.

    Returns:
        Zero-padded 6-digit code.
    """
    code = str(code).strip().lower()
    symbol = re.sub(r"\D", "", code)
    return symbol.zfill(6)


def market_prefix(code: str) -> str:
    """Determine market prefix from ETF code.

    Args:
        code: 6-digit ETF code.

    Returns:
        'sh' for Shanghai, 'sz' for Shenzhen.
    """
    code = normalize_etf_code(code)
    return "sh" if code.startswith(("5", "6")) else "sz"


def read_etf_list(etf_list_path: str) -> pd.DataFrame:
    """Read an ETF list CSV file.

    Args:
        etf_list_path: Path to the ETF list CSV.

    Returns:
        DataFrame with ETF information.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(etf_list_path):
        raise FileNotFoundError(f"ETF list file not found: {etf_list_path}")

    df = pd.read_csv(etf_list_path)
    logger.info(f"Loaded {len(df)} ETF codes")
    return df


def download_batch(
    items: list,
    download_func: Callable,
    output_dir: str,
    file_suffix: str,
    get_id_func: Callable = lambda x: x,
    sleep_range: tuple = (0.5, 2.0),
    desc: str = "Downloading",
    skip_existing: bool = True,
) -> dict:
    """Generic batch download with resume support.

    Args:
        items: List of items to download.
        download_func: Callable that takes a single item and returns a DataFrame.
        output_dir: Output directory for saved files.
        file_suffix: File suffix (e.g. '_nav.csv').
        get_id_func: Function to extract an ID from each item.
        sleep_range: Random sleep range between requests.
        desc: Progress bar description.
        skip_existing: Skip items whose output file already exists.

    Returns:
        Dict with 'success', 'fail', 'skip' counts.
    """
    os.makedirs(output_dir, exist_ok=True)

    stats = {"success": 0, "fail": 0, "skip": 0}

    for item in tqdm(items, desc=desc):
        item_id = get_id_func(item)
        output_file = os.path.join(output_dir, f"{item_id}{file_suffix}")

        if skip_existing and os.path.exists(output_file):
            stats["skip"] += 1
            continue

        try:
            df = download_func(item)
            if df is not None and not df.empty:
                df.to_csv(output_file, index=False, encoding="utf-8-sig")
                stats["success"] += 1
            else:
                logger.warning(f"[{item_id}] returned empty data, skipped.")
                stats["fail"] += 1
        except Exception as e:
            logger.error(f"[{item_id}] download failed: {e}")
            stats["fail"] += 1

        if isinstance(sleep_range, tuple):
            import random

            time.sleep(random.uniform(*sleep_range))
        else:
            time.sleep(sleep_range)

    return stats


def load_column_mapping(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Find the first matching column name from candidates in a DataFrame.

    Args:
        df: DataFrame to search.
        candidates: List of candidate column names.

    Returns:
        The first matching column name, or None if not found.
    """
    for col in candidates:
        if col in df.columns:
            return col
    return None


# Common column name candidates for holdings data
CODE_COL_CANDIDATES = [
    "股票代码",
    "证券代码",
    "代码",
    "stock_code",
    "symbol",
    "基金代码",
]
WEIGHT_COL_CANDIDATES = ["占净值比例", "持仓占比", "权重", "weight", "占比"]
SNAPSHOT_COL_CANDIDATES = ["季度", "日期", "报告期", "持仓日期", "净值日期"]
NAME_COL_CANDIDATES = ["名称", "股票名称", "证券名称", "基金简称"]

# Updated: 2025-03-14

# Updated: 2025-11-19

# Updated: 2025-12-24
