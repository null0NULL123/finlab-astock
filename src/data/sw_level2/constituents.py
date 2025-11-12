"""获取申万二级行业成份股并持久化到 output/。

行业来源:
- 默认读取 `output/sw_level2/sw_level2_industries.csv` (由 industries.py 生成)
- 也可从 AkShare `sw_index_second_info()` 实时获取

成份股来源:
- AkShare `index_component_sw(symbol=...)` (from swsresearch)

注意事项:
- CSV 中行业代码形如 `801016.SI`，`index_component_sw` 需要 `801016` (去除 `.SI` 后缀)。

输出 (默认):
- output/sw_level2/sw_level2_constituents.csv

脚本网络稳健: 每次请求失败后会清除代理环境变量重试一次。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from ...common.proxy_utils import clear_proxy_env, restore_proxy_env


def fetch_sw_level2_industries(*, retry_without_proxy: bool = True) -> pd.DataFrame:
    import akshare as ak

    try:
        return ak.sw_index_second_info()
    except Exception:
        if not retry_without_proxy:
            raise

        old = clear_proxy_env()
        try:
            return ak.sw_index_second_info()
        finally:
            restore_proxy_env(old)


def fetch_sw_index_constituents(
    index_code_no_suffix: str, *, retry_without_proxy: bool = True
) -> pd.DataFrame:
    import akshare as ak

    try:
        return ak.index_component_sw(symbol=index_code_no_suffix)
    except Exception:
        if not retry_without_proxy:
            raise

        old = clear_proxy_env()
        try:
            return ak.index_component_sw(symbol=index_code_no_suffix)
        finally:
            restore_proxy_env(old)


def fetch_sw_index_constituents_legulegu(
    industry_code_with_suffix: str, *, retry_without_proxy: bool = True
) -> pd.DataFrame:
    """Fallback constituents source from LeGuLeGu.

    AkShare exposes this as `sw_index_third_cons`, but in practice the endpoint
    works for many SW industry codes (including level-2).
    """

    import akshare as ak

    try:
        return ak.sw_index_third_cons(symbol=industry_code_with_suffix)
    except Exception:
        if not retry_without_proxy:
            raise

        old = clear_proxy_env()
        try:
            return ak.sw_index_third_cons(symbol=industry_code_with_suffix)
        finally:
            restore_proxy_env(old)


def _standardize_constituents_df(df: pd.DataFrame, *, source: str) -> pd.DataFrame:
    """Normalize different source schemas into a common set of columns."""

    df = df.copy()

    if source == "akshare.index_component_sw":
        # Expected columns: 序号, 证券代码, 证券名称, 最新权重, 计入日期
        if "证券代码" in df.columns:
            df["证券代码"] = df["证券代码"].astype(str).str.zfill(6)
        return df

    if source == "akshare.sw_index_third_cons":
        # Typical columns: 股票代码(带.SZ/.SH), 股票简称, 纳入时间, ...
        if "股票代码" in df.columns and "证券代码" not in df.columns:
            df["证券代码"] = (
                df["股票代码"].astype(str).str.split(".").str[0].str.zfill(6)
            )
        if "股票简称" in df.columns and "证券名称" not in df.columns:
            df["证券名称"] = df["股票简称"].astype(str)
        if "纳入时间" in df.columns and "计入日期" not in df.columns:
            df["计入日期"] = df["纳入时间"]
        if "最新权重" not in df.columns:
            df["最新权重"] = pd.NA
        return df

    return df


def _normalize_industry_code(code: str) -> str:
    # "801016.SI" -> "801016"; already-normalized strings are returned as-is.
    return code.split(".")[0].strip()


def _with_si_suffix(code_no_suffix: str) -> str:
    return f"{code_no_suffix}.SI"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch constituents for SW level-2 industries (申万二级行业成份股)"
    )
    parser.add_argument(
        "--out-dir",
        default="output",
        help="Output directory (default: output)",
    )
    parser.add_argument(
        "--industries-csv",
        default="output/sw_level2/sw_level2_industries.csv",
        help="Path to the SW level-2 industries CSV (default: output/sw_level2/sw_level2_industries.csv)",
    )
    parser.add_argument(
        "--fetch-industries",
        action="store_true",
        help="Fetch industries from AkShare instead of reading --industries-csv",
    )
    parser.add_argument(
        "--csv",
        default="sw_level2_constituents.csv",
        help="CSV filename (default: sw_level2_constituents.csv)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Sleep seconds between requests (default: 0.2)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process first N industries (default: 0 means all)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately if any industry request fails",
    )
    parser.add_argument(
        "--no-proxy-retry",
        action="store_true",
        help="Do not retry after clearing proxy env vars",
    )

    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    retry_without_proxy = not args.no_proxy_retry

    if args.fetch_industries:
        industries_df = fetch_sw_level2_industries(
            retry_without_proxy=retry_without_proxy
        )
    else:
        industries_path = Path(args.industries_csv)
        industries_df = pd.read_csv(
            industries_path, dtype={"行业代码": str}, encoding="utf-8-sig"
        )

    required_cols = {"行业代码", "行业名称", "上级行业"}
    missing = required_cols - set(industries_df.columns)
    if missing:
        raise SystemExit(
            f"Missing required columns in industries data: {sorted(missing)}"
        )

    industries_df = industries_df.copy()
    industries_df["行业代码"] = industries_df["行业代码"].astype(str)

    if args.limit and args.limit > 0:
        industries_df = industries_df.head(args.limit)

    all_rows: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []

    total = len(industries_df)
    for i, row in enumerate(industries_df.to_dict(orient="records"), start=1):
        industry_code = str(row["行业代码"])
        industry_code_no_suffix = _normalize_industry_code(industry_code)

        print(
            f"[{i}/{total}] Fetching constituents: {industry_code} {row.get('行业名称', '')}"
        )

        cons_source = "akshare.index_component_sw"
        try:
            # Retry once more on transient parse issues (e.g. rate-limit HTML).
            try:
                cons_df = fetch_sw_index_constituents(
                    industry_code_no_suffix, retry_without_proxy=retry_without_proxy
                )
            except KeyError:
                time.sleep(1.0)
                cons_df = fetch_sw_index_constituents(
                    industry_code_no_suffix, retry_without_proxy=retry_without_proxy
                )
        except Exception as e:
            # Fallback to LeGuLeGu composition endpoint
            cons_source = "akshare.sw_index_third_cons"
            try:
                cons_df = fetch_sw_index_constituents_legulegu(
                    industry_code
                    if industry_code.endswith(".SI")
                    else _with_si_suffix(industry_code_no_suffix),
                    retry_without_proxy=retry_without_proxy,
                )
            except Exception as e2:
                msg = f"{type(e).__name__}: {e} | fallback {type(e2).__name__}: {e2}"
                errors.append(
                    {
                        "行业代码": industry_code,
                        "行业名称": str(row.get("行业名称", "")),
                        "error": msg,
                    }
                )
                print(f"  ERROR: {msg}")
                if args.fail_fast:
                    raise
                continue

        cons_df = _standardize_constituents_df(cons_df, source=cons_source)

        # Attach industry metadata
        cons_df.insert(0, "行业代码", industry_code)
        cons_df.insert(1, "行业名称", str(row.get("行业名称", "")))
        cons_df.insert(2, "上级行业", str(row.get("上级行业", "")))
        cons_df.insert(3, "来源", cons_source)

        all_rows.append(cons_df)

        if args.sleep and args.sleep > 0:
            time.sleep(args.sleep)

    if all_rows:
        result_df = pd.concat(all_rows, ignore_index=True)
    else:
        result_df = pd.DataFrame(
            columns=[
                "行业代码",
                "行业名称",
                "上级行业",
                "序号",
                "证券代码",
                "证券名称",
                "最新权重",
                "计入日期",
            ]
        )  # empty

    csv_path = out_dir / args.csv
    result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"Wrote: {csv_path} ({len(result_df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Updated: 2025-08-13

# Updated: 2025-11-12
