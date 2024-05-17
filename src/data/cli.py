#!/usr/bin/env python3
"""
数据更新统一入口 CLI

用法:
    python -m src.data.cli                          # 更新全部
    python -m src.data.cli --category etf           # 只更新 ETF
    python -m src.data.cli --category etf fund      # 更新多个类别
    python -m src.data.cli -v                       # 显示子进程完整输出
    python -m src.data.cli --list                   # 列出所有类别和脚本
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = Path(__file__).parent / "fetch_scripts.yaml"


def load_config(path: Path = CONFIG_FILE) -> dict[str, list[dict]]:
    if not path.exists():
        logger.error(f"配置文件不存在: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        logger.error(f"配置文件格式错误: {path}")
        sys.exit(1)
    return config


FETCH_SCRIPTS = load_config()
ALL_CATEGORIES = list(FETCH_SCRIPTS.keys())


def run_script(
    script_path: str, args: list[str], name: str, verbose: bool = False
) -> bool:
    full_path = PROJECT_ROOT / script_path
    if not full_path.exists():
        logger.error(f"脚本不存在: {full_path}")
        return False

    cmd = [sys.executable, str(full_path)] + args
    logger.info(f"运行: {name}")
    logger.debug(f"命令: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=not verbose,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            logger.info(f"✓ {name} 完成")
            return True

        logger.error(f"✗ {name} 失败 (返回码: {result.returncode})")
        if not verbose and result.stderr:
            for line in result.stderr.strip().splitlines()[-5:]:
                logger.error(f"  {line}")
        return False

    except Exception as e:
        logger.error(f"✗ {name} 运行出错: {e}")
        return False


def run_all(
    categories: list[str] | None = None,
    verbose: bool = False,
) -> dict[str, dict[str, bool]]:
    categories = categories or ALL_CATEGORIES

    unknown = set(categories) - set(ALL_CATEGORIES)
    if unknown:
        logger.error(
            f"未知类别: {', '.join(unknown)}，可选: {', '.join(ALL_CATEGORIES)}"
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"开始数据更新，类别: {', '.join(categories)}")
    logger.info("=" * 60)

    all_results: dict[str, dict[str, bool]] = {}
    start = time.time()

    for category in categories:
        logger.info("-" * 60)
        logger.info(f"[{category}]")
        logger.info("-" * 60)

        results: dict[str, bool] = {}
        for cfg in FETCH_SCRIPTS[category]:
            results[cfg["name"]] = run_script(
                cfg["script"], cfg["args"], cfg["name"], verbose
            )
            time.sleep(1)

        all_results[category] = results
        time.sleep(2)

    # 总结
    logger.info("=" * 60)
    total_ok = total_fail = 0
    for cat, res in all_results.items():
        ok = sum(res.values())
        fail = len(res) - ok
        total_ok += ok
        total_fail += fail
        logger.info(f"  {cat}: 成功 {ok}, 失败 {fail}")
    logger.info(
        f"  总计: 成功 {total_ok}, 失败 {total_fail}  耗时 {time.time() - start:.1f}s"
    )
    logger.info("=" * 60)

    return all_results


def list_scripts():
    logger.info("可用的数据更新类别和脚本:")
    logger.info("=" * 60)
    for category, scripts in FETCH_SCRIPTS.items():
        logger.info(f"\n  {category}:")
        for cfg in scripts:
            logger.info(f"    - {cfg['name']}")
            logger.info(f"      脚本: {cfg['script']}")
            logger.info(f"      描述: {cfg['description']}")
    logger.info("\n" + "=" * 60)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="数据更新脚本 - 一键运行所有数据抓取脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--category",
        nargs="+",
        choices=ALL_CATEGORIES,
        default=None,
        help=f"要更新的类别，默认全部。可选: {', '.join(ALL_CATEGORIES)}",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="显示子进程完整输出")
    p.add_argument("--list", action="store_true", help="列出所有可用的类别和脚本")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list:
        list_scripts()
        return 0

    results = run_all(categories=args.category, verbose=args.verbose)

    has_failure = any(
        not ok for cat_results in results.values() for ok in cat_results.values()
    )
    return 1 if has_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
