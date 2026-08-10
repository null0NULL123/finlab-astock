"""
按类别（股票/混合/债券/指数等）抓取公募基金并统计数量，保存合并表与统计摘要。
"""

import sys
import traceback
from pathlib import Path

import akshare as ak
import pandas as pd


def fetch_by_categories(categories, output_dir: Path):
    """按类别抓取公募基金并合并统计

    Args:
        categories: 基金类别列表
        output_dir: 输出目录

    Returns:
        (合并表路径, 统计表路径) 或 (None, None)
    """
    frames = []
    for cat in categories:
        try:
            print(f"抓取类别: {cat}...")
            df = ak.fund_open_fund_rank_em(symbol=cat)
            if df is None:
                print(f"类别 {cat} 未返回数据")
                continue
            df = df.copy()
            df["类别"] = cat
            frames.append(df)
        except Exception:
            print(f"抓取类别 {cat} 失败:")
            traceback.print_exc()
    if not frames:
        print("没有抓到任何类别的数据")
        return None, None
    combined = pd.concat(frames, ignore_index=True)
    # 优先保留每个基金的第一个出现记录
    combined_unique = combined.drop_duplicates(subset=["基金代码"], keep="first")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_combined = output_dir / "all_public_funds_by_category_akshare.csv"
    combined_unique.to_csv(out_combined, index=False)
    counts = (
        combined_unique["类别"]
        .value_counts()
        .rename_axis("类别")
        .reset_index(name="数量")
    )
    out_counts = output_dir / "public_funds_category_counts.csv"
    counts.to_csv(out_counts, index=False)
    return out_combined, out_counts


def main():
    # 项目根目录（从 src/data/fund/ 向上4级）
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    output_dir = repo_root / "output" / "funds"
    categories = [
        "股票型",
        "混合型",
        "债券型",
        "指数型",
        "QDII",
        "LOF",
        "FOF",
    ]
    combined_file, counts_file = fetch_by_categories(categories, output_dir)
    if combined_file is None:
        sys.exit(1)
    print(f"合并表: {combined_file}")
    print(f"统计表: {counts_file}")
    # 打印统计结果
    df_counts = pd.read_csv(counts_file)
    print(df_counts)


if __name__ == "__main__":
    main()



