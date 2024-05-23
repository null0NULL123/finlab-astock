"""
ETF 列表获取器

使用 AkShare 获取全市场 ETF 列表，包含基金代码、基金名称等基本信息。
"""

from __future__ import annotations

from typing import Optional

import akshare as ak
import pandas as pd

from ..base import DataFetcher
from ...common.config import Config

# akshare fund_etf_category_sina 返回的关键列
_REQUIRED_COLUMNS: list[str] = ["基金代码", "基金名称"]


class EtfListFetcher(DataFetcher):
    """全市场 ETF 列表获取器

    通过 AkShare 的 fund_etf_category_sina 接口获取 ETF 基金列表，
    并保存为 parquet 文件供后续分析使用。

    数据源: 新浪财经 - ETF 基金分类
    更新频率: 低频（ETF 列表变动较少，按需更新即可）

    示例:
        >>> fetcher = EtfListFetcher()
        >>> fetcher.run()
    """

    name: str = "etf_list"

    def __init__(self, config: Optional[Config] = None) -> None:
        """初始化 ETF 列表获取器

        Args:
            config: 配置对象，默认使用全局配置
        """
        super().__init__(config)

    def fetch(self) -> pd.DataFrame:
        """从 AkShare 获取全市场 ETF 列表

        调用 fund_etf_category_sina(symbol="ETF基金") 获取数据。

        Returns:
            包含基金代码、基金名称等字段的 DataFrame

        Raises:
            RuntimeError: akshare 接口调用失败
        """
        self.logger.info("正在从 AkShare 获取 ETF 列表...")
        try:
            df: pd.DataFrame = ak.fund_etf_category_sina(symbol="ETF基金")
        except Exception as exc:
            raise RuntimeError(f"获取 ETF 列表失败: {exc}") from exc

        self.logger.info("成功获取 {} 只 ETF", len(df))
        return df

    def validate(self, df: pd.DataFrame) -> bool:
        """验证 ETF 列表数据质量

        校验规则：
        - 数据非空（继承自 DataFetcher）
        - 包含基金代码、基金名称等关键列

        Args:
            df: 待验证的 ETF 列表数据

        Returns:
            True 表示数据有效，False 表示数据异常
        """
        if not super().validate(df):
            return False

        missing: list[str] = [col for col in _REQUIRED_COLUMNS if col not in df.columns]
        if missing:
            self.logger.error("缺少关键列: {}", ", ".join(missing))
            return False

        # 检查基金代码是否有空值
        if df["基金代码"].isna().any():
            self.logger.warning("基金代码列存在空值")

        return True

    def run(self) -> Optional[pd.DataFrame]:
        """执行标准流程：获取 → 验证 → 保存

        保存路径: etf/lists/etf_list.parquet

        Returns:
            验证通过并已保存的 ETF 列表；验证失败或数据为空时返回 None
        """
        return self.fetch_and_save("etf/lists/etf_list.parquet")


if __name__ == "__main__":
    fetcher = EtfListFetcher()
    result: Optional[pd.DataFrame] = fetcher.run()

    if result is not None:
        print("\n=== 数据样本 ===")
        print(result.head(20))
        print(f"\n总计: {len(result)} 只 ETF")
        print(f"列名: {list(result.columns)}")
