"""
使用 AkShare 获取全量公募（开放式）基金列表并保存为 CSV。
"""

import sys
import traceback
from pathlib import Path

import akshare as ak


def fetch_all_open_funds(output_dir: Path):
    """通过 AkShare 东方财富接口获取开放式基金列表

    Args:
        output_dir: 输出目录

    Returns:
        0 表示成功，1 表示无数据，2 表示异常
    """
    try:
        print("正在通过 AkShare 的东方财富接口获取开放式基金列表...")
        df = ak.fund_open_fund_rank_em(symbol="全部")
        if df is None or df.empty:
            print("未获取到数据，请检查网络或 AkShare 安装")
            return 1
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "all_public_funds_akshare.csv"
        df.to_csv(out_file, index=False)
        print(f"已保存到: {out_file}")
        print(f"总计: {len(df)} 条记录")
        print("前 10 条:")
        print(df.head(10))
        return 0
    except Exception as e:
        print("抓取或保存时出错:")
        traceback.print_exc()
        return 2


def main():
    # 项目根目录（从 src/data/fund/ 向上4级）
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    output_dir = repo_root / "output" / "funds"
    rc = fetch_all_open_funds(output_dir)
    sys.exit(rc)


if __name__ == "__main__":
    main()

# Updated: 2025-12-10
