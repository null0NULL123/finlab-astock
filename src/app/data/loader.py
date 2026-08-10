"""数据加载器 — 从 output/ 目录读取分析层输出。

职责：
    - 加载信号文件（JSON）
    - 加载技术指标时序数据（CSV）
    - 加载因子得分（CSV）
    - 加载基本面 / 情绪数据（JSON）
    - 加载宏观状态（JSON）
    - 加载策略决策输出（JSON）
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class DataLoader:
    """从 output/ 目录加载分析数据。

    Attributes:
        output_dir: output/ 目录的绝对路径。
    """

    def __init__(self, output_dir: str | Path = "output") -> None:
        self.output_dir = Path(output_dir).resolve()

    # ------------------------------------------------------------------
    # 信号
    # ------------------------------------------------------------------

    def get_latest_signals(self, asset_type: str | None = None) -> dict:
        """获取最新日期的信号文件。

        Args:
            asset_type: 资产类型 (stock/etf/fund)，为 None 时扫描所有类型。

        Returns:
            信号字典，格式取决于信号文件内容。无数据时返回空 dict。
        """
        if asset_type:
            signals_dir = self.output_dir / asset_type / "signals"
            return self._load_latest_json(signals_dir)

        # 扫描所有资产类型
        result: dict = {}
        for atype in ("stock", "etf", "fund"):
            signals = self.get_latest_signals(asset_type=atype)
            if signals:
                result[atype] = signals
        return result

    # ------------------------------------------------------------------
    # 技术指标
    # ------------------------------------------------------------------

    def get_indicators(
        self,
        symbol: str,
        asset_type: str,
        days: int = 120,
    ) -> pd.DataFrame:
        """获取指定资产的技术指标时序数据。

        Args:
            symbol: 资产代码，如 'SH600519'。
            asset_type: 资产类型 (stock/etf/fund)。
            days: 返回最近 N 天的数据。

        Returns:
            包含 OHLCV 和技术指标的 DataFrame。

        Raises:
            FileNotFoundError: 指标文件不存在。
        """
        # 尝试多种路径模式（兼容实际数据布局）
        symbol_lower = symbol.lower()
        symbol_upper = symbol.upper()
        # 提取纯数字代码（去掉 SH/SZ/BJ 前缀）
        pure_code = symbol_lower.replace("sh", "").replace("sz", "").replace("bj", "")
        candidates = [
            # 标准路径
            self.output_dir / asset_type / "indicators" / f"{symbol}_indicators.csv",
            # 小写代码（ETF 实际布局: sh510300_indicators.csv）
            self.output_dir / asset_type / "indicators" / f"{symbol_lower}_indicators.csv",
            # details/daily 路径（股票实际布局）
            self.output_dir / asset_type / "details" / "daily" / f"{symbol}_daily.csv",
            # 大写变体
            self.output_dir / asset_type / "indicators" / f"{symbol_upper}_indicators.csv",
            # 纯数字代码（基金布局: 000196_indicators.csv）
            self.output_dir / asset_type / "indicators" / f"{pure_code}_indicators.csv",
            # 纯数字 + daily
            self.output_dir / asset_type / "details" / "daily" / f"{pure_code}_daily.csv",
        ]

        path = None
        for p in candidates:
            if p.exists():
                path = p
                break

        if path is None:
            raise FileNotFoundError(
                f"指标文件不存在: {symbol} (尝试了 {len(candidates)} 个路径)"
            )

        df = pd.read_csv(path)

        # 日期列标准化
        if "date" not in df.columns:
            for candidate in ("日期", "trade_date", "Date"):
                if candidate in df.columns:
                    df = df.rename(columns={candidate: "date"})
                    break

        return df.tail(days).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 因子得分
    # ------------------------------------------------------------------

    def get_factors(
        self,
        symbol: str,
        asset_type: str,
        date: str | None = None,
    ) -> dict[str, float]:
        """获取资产的因子得分。

        Args:
            symbol: 资产代码。
            asset_type: 资产类型。
            date: 指定日期 (YYYY-MM-DD)，为 None 时取最新。

        Returns:
            因子名称到得分的映射。无数据时返回空 dict。
        """
        factors_dir = self.output_dir / asset_type / "factors"
        if not factors_dir.exists():
            return {}

        if date:
            path = factors_dir / f"{date}_factors.csv"
        else:
            path = self._find_latest_file(factors_dir, suffix="_factors.csv")

        if path is None or not path.exists():
            return {}

        df = pd.read_csv(path)
        row = df[df.iloc[:, 0].str.contains(symbol, na=False)]
        if row.empty:
            return {}

        # 取第一行，跳过标识列
        return {
            col: float(row.iloc[0][col])
            for col in df.columns[1:]
            if pd.notna(row.iloc[0][col])
        }

    # ------------------------------------------------------------------
    # 基本面 / 情绪
    # ------------------------------------------------------------------

    def get_fundamental(self, symbol: str) -> dict:
        """获取资产基本面数据。

        Args:
            symbol: 资产代码。

        Returns:
            基本面数据字典。无数据时返回基于日线的基础信息。
        """
        # 尝试 qual 层输出
        path = (
            self.output_dir
            / "qual"
            / "fundamentals"
            / f"{symbol}_fundamental.json"
        )
        result = self._load_json(path)
        if result:
            return result

        # 降级：从日线数据提取基础信息
        for daily_dir in ["stock/details/daily", "etf/details/daily"]:
            daily_path = self.output_dir / daily_dir / f"{symbol}_daily.csv"
            if daily_path.exists():
                df = pd.read_csv(daily_path)
                if len(df) > 0:
                    latest = df.iloc[-1]
                    return {
                        "symbol": symbol,
                        "source": "daily_fallback",
                        "latest_date": str(latest.get("日期", latest.get("date", ""))),
                        "close": float(latest.get("收盘", latest.get("close", 0))),
                        "volume": float(latest.get("成交量", latest.get("volume", 0))),
                        "pct_change": float(latest.get("涨跌幅", latest.get("pct_change", 0))),
                        "note": "基本面数据来自日线降级，完整分析需运行 qual 层",
                    }
        return {}

    def get_sentiment(self, symbol: str) -> dict:
        """获取资产情绪指标。

        Args:
            symbol: 资产代码。

        Returns:
            情绪数据字典。无数据时返回空 dict。
        """
        path = (
            self.output_dir
            / "qual"
            / "sentiment"
            / f"{symbol}_sentiment.json"
        )
        result = self._load_json(path)
        if result:
            return result

        # 降级：返回占位数据
        return {
            "symbol": symbol,
            "source": "placeholder",
            "sentiment_score": 0.0,
            "state": "中性",
            "note": "情绪数据未生成，需运行 qual 层或接入舆情数据源",
        }

    # ------------------------------------------------------------------
    # 宏观状态
    # ------------------------------------------------------------------

    def get_macro_regime(self, date: str | None = None) -> dict:
        """获取宏观状态判断。

        Args:
            date: 指定日期，为 None 时取最新。

        Returns:
            宏观状态字典。无数据时基于 CSV 宏观数据生成概要。
        """
        # 尝试 qual 层输出
        macro_dir = self.output_dir / "qual" / "macro"
        if macro_dir.exists():
            if date:
                path = macro_dir / f"{date}_macro_regime.json"
            else:
                path = self._find_latest_file(macro_dir, suffix="_macro_regime.json")
            result = self._load_json(path) if path else {}
            if result:
                return result

        # 降级：从 output/macro/ CSV 文件读取宏观数据概要
        macro_csv_dir = self.output_dir / "macro"
        if not macro_csv_dir.exists():
            return {}

        summary: dict = {"source": "csv_fallback", "indicators": {}}
        for csv_file in sorted(macro_csv_dir.glob("*.csv")):
            name = csv_file.stem.replace("macro_", "")
            try:
                df = pd.read_csv(csv_file)
                if len(df) > 0:
                    latest = df.iloc[-1].to_dict()
                    summary["indicators"][name] = latest
            except Exception:
                pass

        return summary

    # ------------------------------------------------------------------
    # 行业数据
    # ------------------------------------------------------------------

    def get_sw_level2_data(self, filename: str) -> pd.DataFrame:
        """获取申万二级行业数据。

        Args:
            filename: 文件名，如 'industry_return.csv'。

        Returns:
            行业数据 DataFrame。

        Raises:
            FileNotFoundError: 文件不存在。
        """
        path = self.output_dir / "sw_level2" / filename
        if not path.exists():
            raise FileNotFoundError(f"行业数据文件不存在: {path}")
        return pd.read_csv(path)

    # ------------------------------------------------------------------
    # 策略输出
    # ------------------------------------------------------------------

    def get_strategy_decisions(self) -> list[dict]:
        """获取所有策略决策摘要，按时间倒序排列。

        Returns:
            决策摘要列表，每项包含 symbol, action, risk_score, risk_verdict,
            position_size, timestamp, filepath 等字段。
        """
        strategy_dir = self.output_dir / "strategy"
        if not strategy_dir.exists():
            return []

        results: list[dict] = []
        for json_file in sorted(strategy_dir.glob("*.json"), reverse=True):
            data = self._load_json(json_file)
            if not data:
                continue
            meta = data.get("meta", {})
            decision = data.get("decision", {})
            results.append({
                "symbol": meta.get("symbol", json_file.stem.split("_")[0]),
                "asset_type": meta.get("asset_type", ""),
                "action": decision.get("action", ""),
                "risk_score": decision.get("risk_score", 0),
                "risk_verdict": decision.get("risk_verdict", ""),
                "position_size": decision.get("position_size", 0),
                "timestamp": meta.get("timestamp", ""),
                "llm": meta.get("llm", ""),
                "filepath": str(json_file),
            })
        return results

    def load_strategy_detail(self, filepath: str | Path) -> dict:
        """加载单个策略决策的完整内容。

        Args:
            filepath: 策略 JSON 文件路径。

        Returns:
            完整的策略数据字典（meta + decision + reports）。
        """
        path = Path(filepath)
        if not path.exists():
            return {}
        return self._load_json(path)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: Path) -> dict:
        """安全加载 JSON 文件。"""
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _load_latest_json(directory: Path) -> dict:
        """加载目录下最新的 JSON 文件（按文件名排序）。"""
        if not directory.exists():
            return {}
        files = sorted(directory.glob("*.json"), reverse=True)
        if not files:
            return {}
        with open(files[0], encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _find_latest_file(directory: Path, suffix: str) -> Path | None:
        """查找目录下匹配后缀的最新文件。"""
        if not directory.exists():
            return None
        files = sorted(directory.glob(f"*{suffix}"), reverse=True)
        return files[0] if files else None


