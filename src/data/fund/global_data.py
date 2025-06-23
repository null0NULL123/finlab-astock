"""
一次性拉取全局的基金经理变动、份额规模变动等宏观统计数据表。
"""

import akshare as ak
import pandas as pd
from pathlib import Path


def download_globals():
    """拉取全市场基金经理变动和份额规模变动数据"""
    # 项目根目录（从 src/data/fund/ 向上4级）
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    out_dir = repo_root / "output" / "funds" / "fund_market_data"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("开始拉取【全市场基金经理变动明细】 (约数万条, 需请求较长时间)...")
    try:
        df_mgr = ak.fund_manager_em()
        mgr_file = out_dir / "all_fund_managers_em.csv"
        df_mgr.to_csv(mgr_file, index=False)
        print(f"已保存: {mgr_file} ({len(df_mgr)} 行)")
    except Exception as e:
        print(f"获取失败: {e}")

    print("\n开始拉取【全市场基金份额规模历史变动】...")
    try:
        df_scale = ak.fund_scale_change_em()
        scale_file = out_dir / "all_fund_scale_change_em.csv"
        df_scale.to_csv(scale_file, index=False)
        print(f"已保存: {scale_file} ({len(df_scale)} 行)")
    except Exception as e:
        print(f"获取失败: {e}")


if __name__ == "__main__":
    download_globals()

# Updated: 2025-06-23
