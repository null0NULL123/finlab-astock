"""
股票历史日线数据获取器

支持两种数据源:
    1. baostock (默认, 无需网络代理, 免费)
    2. akshare (需直连东方财富 API)
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

import pandas as pd

from ..base import DataFetcher
from ...common.config import Config
from ...common.stock_utils import normalize_symbol, symbol_to_baostock

# 内置热门股票列表 (覆盖主要行业板块)
POPULAR_STOCKS: List[str] = [
    # 白酒
    "600519",  # 贵州茅台
    "000858",  # 五粮液
    "000568",  # 泸州老窖
    # 银行
    "600036",  # 招商银行
    "601318",  # 中国平安
    "601166",  # 兴业银行
    # 新能源
    "300750",  # 宁德时代
    "002594",  # 比亚迪
    "601012",  # 隆基绿能
    # 科技/半导体
    "002415",  # 海康威视
    "603986",  # 兆易创新
    "002230",  # 科大讯飞
    # 医药
    "600276",  # 恒瑞医药
    "300760",  # 迈瑞医疗
    "000538",  # 云南白药
    # 消费
    "000333",  # 美的集团
    "600887",  # 伊利股份
    "002714",  # 牧原股份
    # 基建/地产
    "600048",  # 保利发展
    "601668",  # 中国建筑
    # 证券
    "600030",  # 中信证券
    "601688",  # 华泰证券
    # 电力
    "600900",  # 长江电力
    "601985",  # 中国核电
    # 通信
    "600941",  # 中国移动
    "000063",  # 中兴通讯
]


class StockDailyFetcher(DataFetcher):
    """股票历史日线数据获取器

    通过 baostock 或 akshare 逐只获取股票日线数据（不复权），
    合并为一张大表后保存为 parquet 文件。

    数据源: baostock (默认) / akshare
    更新频率: 日频（每个交易日收盘后更新）

    示例:
        >>> fetcher = StockDailyFetcher(codes=["600519", "000858"])
        >>> fetcher.run()

        >>> fetcher = StockDailyFetcher(use_popular=True, source="akshare")
        >>> fetcher.run()
    """

    name: str = "stock_daily"

    def __init__(
        self,
        config: Optional[Config] = None,
        codes: Optional[List[str]] = None,
        use_popular: bool = False,
        start_date: str = "",
        end_date: str = "",
        source: str = "baostock",
        sleep: float = 0.3,
    ) -> None:
        """初始化股票日线获取器

        Args:
            config: 配置对象，默认使用全局配置
            codes: 股票代码列表，如 ["600519", "SH600519"]
            use_popular: 使用内置热门股票列表（与 codes 二选一）
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            source: 数据源 - 'baostock' (默认) 或 'akshare'
            sleep: 每次请求间隔秒数
        """
        super().__init__(config)
        if not codes and not use_popular:
            raise ValueError("必须提供 codes 或设置 use_popular=True")
        self.codes = codes or []
        self.use_popular = use_popular
        self.start_date = start_date
        self.end_date = end_date
        self.source = source
        self.sleep = sleep

    def _resolve_codes(self) -> List[str]:
        """解析股票代码列表"""
        if self.use_popular:
            return POPULAR_STOCKS
        return self.codes

    def _clear_proxy_for_baostock(self) -> None:
        """清除代理环境变量（baostock 需要直连）"""
        for key in [
            "HTTP_PROXY", "HTTPS_PROXY",
            "http_proxy", "https_proxy",
            "ALL_PROXY", "all_proxy",
        ]:
            os.environ.pop(key, None)

    def _fetch_one_baostock(self, code: str, start: str, end: str) -> pd.DataFrame:
        """使用 baostock 获取单只股票日线数据"""
        import baostock as bs

        symbol = normalize_symbol(code)
        bs_code = symbol_to_baostock(symbol)

        start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
        end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"

        lg = bs.login()
        if lg.error_code != "0":
            raise ConnectionError(f"Baostock login failed: {lg.error_msg}")

        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount",
                start_date=start_fmt,
                end_date=end_fmt,
                frequency="d",
                adjustflag="3",  # 不复权
            )

            if rs.error_code != "0":
                raise ValueError(f"Query failed: {rs.error_msg}")

            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                return pd.DataFrame()

            df = pd.DataFrame(
                data_list,
                columns=["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"],
            )

            for col in ["开盘", "收盘", "最高", "最低", "成交量", "成交额"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # 去除停牌日 (volume=0)
            df = df[df["成交量"] > 0].reset_index(drop=True)

            df["symbol"] = symbol
            return df

        finally:
            bs.logout()

    def _fetch_one_akshare(self, code: str, start: str, end: str) -> pd.DataFrame:
        """使用 akshare 获取单只股票日线数据"""
        import akshare as ak

        symbol = normalize_symbol(code)
        raw_symbol = symbol[-6:]

        df = ak.stock_zh_a_hist(
            symbol=raw_symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="",  # 不复权
        )

        if df.empty:
            return df

        df["symbol"] = symbol
        return df

    def fetch(self) -> pd.DataFrame:
        """逐只下载股票日线数据并合并

        Returns:
            包含所有股票日线数据的 DataFrame

        Raises:
            RuntimeError: 全部股票获取失败
        """
        codes = self._resolve_codes()
        self.logger.info("开始下载 {} 只股票日线数据 (source={})", len(codes), self.source)

        if self.source == "baostock":
            self._clear_proxy_for_baostock()
            fetch_one = self._fetch_one_baostock
        elif self.source == "akshare":
            fetch_one = self._fetch_one_akshare
        else:
            raise ValueError(f"不支持的数据源: {self.source}")

        frames: list[pd.DataFrame] = []
        success = fail = 0

        for i, raw_code in enumerate(codes):
            try:
                symbol = normalize_symbol(raw_code)
                self.logger.info("[{}/{}] {} ...", i + 1, len(codes), symbol)

                df = fetch_one(raw_code, self.start_date, self.end_date)
                if df is not None and not df.empty:
                    frames.append(df)
                    success += 1
                else:
                    self.logger.warning("[{}] {} 返回空数据，已跳过", symbol, raw_code)
                    fail += 1
            except Exception as e:
                self.logger.error("[{}] 获取失败: {}", raw_code, e)
                fail += 1

            if i < len(codes) - 1:
                time.sleep(self.sleep)

        self.logger.info("下载完成: 成功 {}, 失败 {}", success, fail)

        if not frames:
            raise RuntimeError("全部股票获取失败，无可用数据")

        return pd.concat(frames, ignore_index=True)

    def validate(self, df: pd.DataFrame) -> bool:
        """验证日线数据质量

        校验规则：
        - 数据非空（继承自 DataFetcher）
        - 包含 symbol、日期 关键列
        - 数值列无全 NaN

        Args:
            df: 待验证的数据

        Returns:
            True 表示数据有效，False 表示数据异常
        """
        if not super().validate(df):
            return False

        required = ["symbol", "日期"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            self.logger.error("缺少关键列: {}", ", ".join(missing))
            return False

        numeric_cols = ["开盘", "收盘", "最高", "最低"]
        for col in numeric_cols:
            if col in df.columns and df[col].isna().all():
                self.logger.error("列 {} 全为 NaN", col)
                return False

        return True

    def run(self) -> Optional[pd.DataFrame]:
        """执行标准流程：获取 → 验证 → 保存

        保存路径: stock/daily/stock_daily.parquet

        Returns:
            验证通过并已保存的数据；验证失败或数据为空时返回 None
        """
        return self.fetch_and_save("stock/daily/stock_daily.parquet")


if __name__ == "__main__":
    fetcher = StockDailyFetcher(
        codes=["600519", "000858"],
        start_date="20240101",
        end_date="20250101",
    )
    result = fetcher.run()

    if result is not None:
        print(f"\n=== 数据概览 ===")
        print(f"总行数: {len(result)}")
        print(f"股票数量: {result['symbol'].nunique()}")
        print(f"列名: {list(result.columns)}")
        print(result.head())

# Updated: 2025-05-08

# Updated: 2025-07-23

# Updated: 2025-07-24
