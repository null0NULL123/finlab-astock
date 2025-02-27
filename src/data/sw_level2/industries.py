"""获取申万二级行业列表并持久化到 output/。

数据源: AkShare `sw_index_second_info()`。

输出 (默认):
- output/sw_level2/sw_level2_industries.csv
- output/sw_level2/sw_level2_industries.json

本脚本依赖轻量且网络稳健: 首次失败后会清除代理环境变量重试一次。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ...common.proxy_utils import clear_proxy_env, restore_proxy_env


def fetch_sw_level2_industries(*, retry_without_proxy: bool = True):
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch SW level-2 industries (申万二级行业)"
    )
    parser.add_argument(
        "--out-dir",
        default="output/sw_level2",
        help="Output directory (default: output/sw_level2)",
    )
    parser.add_argument(
        "--csv",
        default="sw_level2_industries.csv",
        help="CSV filename (default: sw_level2_industries.csv)",
    )
    parser.add_argument(
        "--json",
        default="sw_level2_industries.json",
        help="JSON filename (default: sw_level2_industries.json)",
    )
    parser.add_argument(
        "--no-proxy-retry",
        action="store_true",
        help="Do not retry after clearing proxy env vars",
    )

    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = fetch_sw_level2_industries(retry_without_proxy=not args.no_proxy_retry)

    csv_path = out_dir / args.csv
    json_path = out_dir / args.json

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    records = df.to_dict(orient="records")
    json_path.write_text(
        json.dumps(
            {
                "source": "akshare.sw_index_second_info",
                "rows": len(records),
                "data": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote: {csv_path} ({len(df)} rows)")
    print(f"Wrote: {json_path} ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Updated: 2025-02-27
