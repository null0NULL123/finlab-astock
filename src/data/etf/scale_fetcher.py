"""
ETF 规模数据获取器

使用 AkShare 获取全市场 ETF 的最新规模信息（总市值、流通市值等）。
"""

from __future__ import annotations

from typing import Optional

import akshare as ak
import pandas as pd

from ..base import DataFetcher
from ...common.config import Config


class EtfScaleFetcher(DataFetcher):
    """ETF 规模数据获取器

    通过 AkShare 的 fund_etf_spot_em 接口获取全市场 ETF 实时行情，
    提取规模相关字段（总市值、流通市值等）后保存为 parquet 文件。

    数据源: 东方财富 - ETF 实时行情（含规模）
    更新频率: 日频（盘中实时，收盘后定格）

    示例:
        >>> fetcher = EtfScaleFetcher()
        >>> fetcher.run()
    """

    name: str = "etf_scale"

    # 保留的主要列
    SCALE_COLS = ["代码", "名称", "最新价", "总市值", "流通市值", "基金折价率", "换手率"]

    def __init__(self, config: Optional[Config] = None) -> None:
        """初始化 ETF 规模获取器

        Args:
            config: 配置对象，默认使用全局配置
        """
        super().__init__(config)

    def fetch(self) -> pd.DataFrame:
        """获取全市场 ETF 规模数据

        调用 fund_etf_spot_em 获取 ETF 实时行情，
        筛选规模相关列并按总市值降序排列。

        Returns:
            包含 ETF 规模信息的 DataFrame

        Raises:
            RuntimeError: 接口返回空数据
        """
        self.logger.info("正在从 AkShare 获取 ETF 规模数据...")

        df = ak.fund_etf_spot_em()
        if df is None or df.empty:
            raise RuntimeError("fund_etf_spot_em 返回空数据")

        self.logger.info("成功获取 {} 只 ETF 数据", len(df))

        # 筛选可用列
        available_cols = [c for c in self.SCALE_COLS if c in df.columns]
        if not available_cols:
            self.logger.warning("预期列均不存在，保留全部列")
            available_cols = list(df.columns)

        df_scale = df[available_cols].copy()

        # 按总市值降序排列
        if "总市值" in df_scale.columns:
            df_scale["总市值"] = pd.to_numeric(df_scale["总市值"], errors="coerce")
            df_scale = df_scale.sort_values(by="总市值", ascending=False)

        return df_scale

    def validate(self, df: pd.DataFrame) -> bool:
        """验证 ETF 规模数据质量

        校验规则：
        - 数据非空（继承自 DataFetcher）
        - 包含 代码 列

        Args:
            df: 待验证的数据

        Returns:
            True 表示数据有效，False 表示数据异常
        """
        if not super().validate(df):
            return False

        if "代码" not in df.columns:
            self.logger.error("缺少关键列: 代码")
            return False

        return True

    def run(self) -> Optional[pd.DataFrame]:
        """执行标准流程：获取 → 验证 → 保存

        保存路径: etf/scale/etf_scale.parquet

        Returns:
            验证通过并已保存的数据；验证失败或数据为空时返回 None
        """
        return self.fetch_and_save("etf/scale/etf_scale.parquet")


if __name__ == "__main__":
    fetcher = EtfScaleFetcher()
    result = fetcher.run()

    if result is not None:
        print(f"\n=== 数据概览 ===")
        print(f"总行数: {len(result)}")
        print(f"列名: {list(result.columns)}")
        if "总市值" in result.columns:
            print("\n规模最大的前 10 只 ETF:")
            print(result[["代码", "名称", "总市值"]].head(10))




