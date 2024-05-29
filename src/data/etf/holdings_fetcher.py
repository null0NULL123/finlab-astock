"""
ETF 持仓数据获取器

使用 AkShare 逐只下载 ETF 的最新持仓信息，合并为一张大表。
"""

from __future__ import annotations

import datetime
import re
import time
from typing import Optional

import akshare as ak
import pandas as pd

from ..base import DataFetcher
from ...common.config import Config


class EtfHoldingsFetcher(DataFetcher):
    """ETF 持仓数据获取器

    通过 AkShare 的 fund_portfolio_hold_em 接口逐只获取 ETF 持仓数据，
    合并为一张大表后保存为 parquet 文件。

    数据源: 东方财富 - ETF 持仓明细
    更新频率: 季频（基金季报/半年报/年报披露后更新）

    示例:
        >>> fetcher = EtfHoldingsFetcher()
        >>> fetcher.run()
    """

    name: str = "etf_holdings"

    def __init__(
        self,
        config: Optional[Config] = None,
        etf_list_path: Optional[str] = None,
        year: Optional[str] = None,
        sleep: float = 1.0,
    ) -> None:
        """初始化 ETF 持仓获取器

        Args:
            config: 配置对象，默认使用全局配置
            etf_list_path: ETF 列表 CSV 路径，为 None 时使用默认路径
            year: 持仓年份，为空时默认当前年份
            sleep: 每次请求间隔秒数
        """
        super().__init__(config)
        self.etf_list_path = etf_list_path
        self.year = year or str(datetime.date.today().year)
        self.sleep = sleep

    def _resolve_etf_list_path(self):
        """解析 ETF 列表文件路径"""
        from pathlib import Path

        if self.etf_list_path:
            return Path(self.etf_list_path)
        return self.config.get_output_path("etf", "lists", "all_etfs_akshare.csv")

    def fetch(self) -> pd.DataFrame:
        """逐只下载 ETF 持仓数据并合并

        读取 ETF 列表，逐只调用 fund_portfolio_hold_em 获取持仓，
        最终合并为一张大表。

        Returns:
            包含所有 ETF 持仓的 DataFrame，含 代码/名称 列

        Raises:
            FileNotFoundError: ETF 列表文件不存在
            RuntimeError: 全部 ETF 获取失败
        """
        list_path = self._resolve_etf_list_path()
        if not list_path.exists():
            raise FileNotFoundError(
                f"ETF列表文件不存在: {list_path}。请先运行 EtfListFetcher 获取列表。"
            )

        df_etf = pd.read_csv(list_path)
        self.logger.info("读取 {} 只 ETF，开始下载持仓数据...", len(df_etf))

        frames: list[pd.DataFrame] = []
        success = fail = 0

        for _, row in df_etf.iterrows():
            raw_code = str(row["代码"]).strip().lower()
            name = str(row.get("名称", "")).strip()
            symbol = re.sub(r"\D", "", raw_code).zfill(6)

            try:
                df_hold = ak.fund_portfolio_hold_em(symbol=symbol, date=self.year)
                if df_hold is not None and not df_hold.empty:
                    df_hold.insert(0, "代码", raw_code)
                    df_hold.insert(1, "名称", name)
                    frames.append(df_hold)
                    success += 1
                else:
                    self.logger.warning("[{}] {} 返回空数据，已跳过", raw_code, name)
                    fail += 1
            except Exception as e:
                self.logger.error("[{}] {} 获取失败: {}", raw_code, name, e)
                fail += 1

            time.sleep(self.sleep)

        self.logger.info("下载完成: 成功 {}, 失败 {}", success, fail)

        if not frames:
            raise RuntimeError("全部 ETF 获取失败，无可用数据")

        return pd.concat(frames, ignore_index=True)

    def validate(self, df: pd.DataFrame) -> bool:
        """验证 ETF 持仓数据质量

        校验规则：
        - 数据非空（继承自 DataFetcher）
        - 包含 代码、名称 关键列

        Args:
            df: 待验证的数据

        Returns:
            True 表示数据有效，False 表示数据异常
        """
        if not super().validate(df):
            return False

        required = ["代码", "名称"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            self.logger.error("缺少关键列: {}", ", ".join(missing))
            return False

        return True

    def run(self) -> Optional[pd.DataFrame]:
        """执行标准流程：获取 → 验证 → 保存

        保存路径: etf/holdings/etf_holdings.parquet

        Returns:
            验证通过并已保存的数据；验证失败或数据为空时返回 None
        """
        return self.fetch_and_save("etf/holdings/etf_holdings.parquet")


if __name__ == "__main__":
    fetcher = EtfHoldingsFetcher()
    result = fetcher.run()

    if result is not None:
        print(f"\n=== 数据概览 ===")
        print(f"总行数: {len(result)}")
        print(f"ETF 数量: {result['代码'].nunique()}")
        print(f"列名: {list(result.columns)}")
        print(result.head())
