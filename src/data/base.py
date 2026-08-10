"""
数据层基类

提供带验证和增量更新能力的数据获取器，继承自通用 BaseFetcher。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from ..common.base import BaseFetcher
from ..common.config import Config


class DataFetcher(BaseFetcher):
    """数据层获取基类

    在 BaseFetcher 基础上增加数据验证和增量更新能力。
    子类只需实现 fetch()，可选覆盖 validate() 添加自定义校验逻辑。

    子类示例:
        class EtfNavFetcher(DataFetcher):
            name = "etf_nav"

            def fetch(self) -> pd.DataFrame:
                return ak.fund_etf_fund_info_em()

            def validate(self, df: pd.DataFrame) -> bool:
                if not super().validate(df):
                    return False
                if "基金代码" not in df.columns:
                    self.logger.error("缺少基金代码列")
                    return False
                return True

            def run(self):
                self.fetch_and_save("etf/nav.parquet")
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        """初始化数据获取器

        Args:
            config: 配置对象，默认使用全局配置
        """
        super().__init__(config)

    def validate(self, df: pd.DataFrame) -> bool:
        """验证数据质量（子类可覆盖）

        默认校验：数据非 None 且非空。

        Args:
            df: 待验证的数据

        Returns:
            True 表示数据有效，False 表示数据异常
        """
        if df is None or df.empty:
            self.logger.warning("数据验证失败: 数据为空")
            return False
        return True

    def incremental_update(
        self,
        relative_path: str,
        force: bool = False,
    ) -> pd.DataFrame:
        """增量更新：文件已存在则直接加载，否则获取新数据

        Args:
            relative_path: 相对于 output_dir 的路径
            force: 强制重新获取，忽略已有文件

        Returns:
            已有数据或新获取的数据
        """
        path = self.config.get_output_path(relative_path)

        if not force and self.storage.exists(path):
            self.logger.info("文件已存在，跳过获取: {}", path.name)
            return self.load(relative_path)

        self.logger.info("开始获取数据: {}", relative_path)
        df = self.fetch()
        if df is not None and not df.empty:
            self.save(df, relative_path)
        return df

    def fetch_and_save(
        self,
        relative_path: str,
        force: bool = False,
    ) -> Optional[pd.DataFrame]:
        """标准流程：获取 → 验证 → 保存

        Args:
            relative_path: 相对于 output_dir 的保存路径
            force: 强制重新获取，忽略已有文件

        Returns:
            验证通过并已保存的数据；验证失败或数据为空时返回 None
        """
        path = self.config.get_output_path(relative_path)

        if not force and self.storage.exists(path):
            self.logger.info("文件已存在，跳过获取: {}", path.name)
            return self.load(relative_path)

        self.logger.info("开始获取数据: {}", self.name)
        try:
            df = self.fetch()
            if df is None or df.empty:
                self.logger.warning("获取到空数据: {}", self.name)
                return None

            if not self.validate(df):
                self.logger.error("数据验证失败，跳过保存: {}", self.name)
                return None

            self.save(df, relative_path)
            self.logger.info("完成: {} ({}行)", self.name, len(df))
            return df
        except Exception:
            self.logger.exception("获取数据失败: {}", self.name)
            raise

