"""抓取宏观数据(AkShare)并落地到 output/macro/

依赖 AkShare 宏观数据接口，提供统一 CLI：
    --list   列出可用宏观数据集(按名称过滤)
    --dataset 抓取一个或多个数据集(函数名)，默认抓取一组常用中国宏观指标

示例:
    python -m src.data.macro.fetcher --list --pattern china_cpi
    python -m src.data.macro.fetcher
    python -m src.data.macro.fetcher --dataset macro_china_cpi_monthly --dataset macro_china_ppi

说明: AkShare/requests 在设置了代理环境变量时偶发卡住，默认失败后会再试一次(清空代理)。
支持 --no-proxy 在整个运行期间清空代理。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

from ...common.proxy_utils import cleared_proxy_env

DEFAULT_DATASETS: list[str] = [
    "macro_china_cpi_monthly",
    "macro_china_ppi",
    "macro_china_ppi_yearly",
    "macro_china_gdp_yearly",
    "macro_china_pmi_yearly",
    "macro_china_cx_pmi_yearly",
    "macro_china_lpr",
    "macro_bank_china_interest_rate",
]


@contextmanager
def _default_timeout(seconds: float):
    """临时给 requests.Session.request 注入默认 timeout。"""
    if seconds <= 0:
        yield
        return
    import requests

    old = requests.sessions.Session.request

    def _patched(session, method, url, **kw):
        kw.setdefault("timeout", seconds)
        return old(session, method, url, **kw)

    requests.sessions.Session.request = _patched  # type: ignore[assignment]
    try:
        yield
    finally:
        requests.sessions.Session.request = old  # type: ignore[assignment]


def _safe_filename(s: str) -> str:
    return re.sub(r'[/\\:*?"<>|\s]+', "_", str(s).strip())[:200]


def _iter_ak_datasets(pattern: str | None) -> list[str]:
    import akshare as ak

    pat = (pattern or "").strip().lower()
    return sorted(
        [
            name
            for name in dir(ak)
            if callable(getattr(ak, name, None))
            and (name.startswith("macro_") or name.startswith("index_pmi"))
            and (not pat or pat in name.lower())
        ],
        key=str.lower,
    )


def _load_kwargs_json(s: str | None) -> dict[str, dict[str, Any]]:
    if not s or not s.strip():
        return {}
    try:
        obj = json.loads(s)
    except Exception as e:
        raise SystemExit(f"Invalid --kwargs-json (must be JSON): {e}")
    if not isinstance(obj, dict):
        raise SystemExit(
            "--kwargs-json must be a JSON object mapping dataset -> kwargs dict"
        )
    out: dict[str, dict[str, Any]] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or not k.strip():
            raise SystemExit("--kwargs-json keys must be non-empty strings")
        out[k] = v if isinstance(v, dict) else {}
    return out


def fetch_one_dataset(
    *,
    dataset: str,
    kwargs: dict[str, Any] | None,
    retry_without_proxy: bool,
    timeout: float,
):
    import akshare as ak
    import pandas as pd

    fn = getattr(ak, dataset, None)
    if fn is None or not callable(fn):
        raise SystemExit(f"Unknown AkShare dataset: {dataset}")

    def _call():
        with _default_timeout(timeout):
            df = fn(**(kwargs or {}))
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"{dataset} returned non-DataFrame: {type(df)}")
        return df

    try:
        return _call()
    except Exception:
        if not retry_without_proxy:
            raise
        with cleared_proxy_env():
            return _call()


def main() -> int:
    p = argparse.ArgumentParser(
        description="抓取宏观数据(AkShare)并落地到 output/macro/"
    )
    p.add_argument(
        "--dataset", action="append", default=None, help="数据集函数名(可重复)"
    )
    p.add_argument("--list", action="store_true", help="列出可用数据集并退出")
    p.add_argument("--pattern", default=None, help="配合 --list: 按名称子串过滤")
    p.add_argument(
        "--kwargs-json", default=None, help='JSON: {"dataset": {"arg": "val"}}'
    )
    p.add_argument(
        "--out-dir", default="output/macro", help="输出目录 (default: output/macro)"
    )
    p.add_argument(
        "--timeout", type=float, default=20.0, help="HTTP 超时秒数 (default: 20)"
    )
    p.add_argument(
        "--sleep", type=float, default=0.2, help="数据集间 sleep 秒数 (default: 0.2)"
    )
    p.add_argument("--no-proxy", action="store_true", help="整个运行期间清空代理")
    args = p.parse_args()

    if args.list:
        names = _iter_ak_datasets(args.pattern)
        print(*names, sep="\n")
        print(f"Total: {len(names)}")
        return 0

    datasets = [
        str(d).strip() for d in (args.dataset or DEFAULT_DATASETS) if str(d).strip()
    ]
    if not datasets:
        raise SystemExit("No datasets specified")

    kwargs_map = _load_kwargs_json(args.kwargs_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ctx = cleared_proxy_env() if args.no_proxy else nullcontext()
    total_rows = 0

    with ctx:
        for i, dataset in enumerate(datasets, 1):
            df = fetch_one_dataset(
                dataset=dataset,
                kwargs=kwargs_map.get(dataset),
                retry_without_proxy=True,
                timeout=args.timeout,
            )
            out_path = out_dir / f"{_safe_filename(dataset)}.csv"
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            total_rows += len(df)
            print(
                f"[{i}/{len(datasets)}] Wrote: {out_path} ({len(df)} rows, {len(df.columns)} cols)"
            )
            if args.sleep > 0 and i < len(datasets):
                time.sleep(args.sleep)

    print(
        f"Done. Datasets: {len(datasets)}, total rows: {total_rows}, out_dir: {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
