"""
计算公募基金的技术指标。

基于已下载的基金净值数据，计算如MA, MACD, RSI, BOLL等基于连续单价数据的技术指标。
注意：由于公募基金只有每日的单位净值，没有高、低、开盘价和成交量数据，
因此只能计算部分不需要这几项数据的指标。
"""

import argparse
import logging
import os
from typing import Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class FundTechnicalIndicators:
    """基金技术指标计算器"""

    @staticmethod
    def calculate_ma(
        data: pd.DataFrame, periods: list = [5, 10, 20, 30, 60, 120, 250]
    ) -> pd.DataFrame:
        """计算移动平均线 (Moving Average)"""
        for period in periods:
            data[f"MA{period}"] = data["单位净值"].rolling(window=period).mean()
        return data

    @staticmethod
    def calculate_ema(
        data: pd.DataFrame, periods: list = [5, 10, 20, 30, 60, 120]
    ) -> pd.DataFrame:
        """计算指数移动平均线 (Exponential Moving Average)"""
        for period in periods:
            data[f"EMA{period}"] = (
                data["单位净值"].ewm(span=period, adjust=False).mean()
            )
        return data

    @staticmethod
    def calculate_rsi(data: pd.DataFrame, periods: list = [6, 12, 24]) -> pd.DataFrame:
        """计算相对强弱指标 (Relative Strength Index)"""
        for period in periods:
            delta = data["单位净值"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            data[f"RSI{period}"] = 100 - (100 / (1 + rs))
            # 填补分母为0的情况
            data[f"RSI{period}"] = data[f"RSI{period}"].fillna(100)

        return data

    @staticmethod
    def calculate_macd(
        data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        """计算MACD指标"""
        fast_ema = data["单位净值"].ewm(span=fast, adjust=False).mean()
        slow_ema = data["单位净值"].ewm(span=slow, adjust=False).mean()
        data["MACD_DIF"] = fast_ema - slow_ema
        data["MACD_DEA"] = data["MACD_DIF"].ewm(span=signal, adjust=False).mean()
        data["MACD_BAR"] = (data["MACD_DIF"] - data["MACD_DEA"]) * 2
        return data

    @staticmethod
    def calculate_boll(
        data: pd.DataFrame, window: int = 20, num_std: float = 2.0
    ) -> pd.DataFrame:
        """计算布林带 (Bollinger Bands)"""
        data["BOLL_MID"] = data["单位净值"].rolling(window=window).mean()
        rolling_std = data["单位净值"].rolling(window=window).std()
        data["BOLL_UP"] = data["BOLL_MID"] + (rolling_std * num_std)
        data["BOLL_DOWN"] = data["BOLL_MID"] - (rolling_std * num_std)
        data["BOLL_WIDTH"] = (
            (data["BOLL_UP"] - data["BOLL_DOWN"]) / data["BOLL_MID"] * 100
        )
        # 防止除0
        data["BOLL_PERCENT"] = np.where(
            data["BOLL_UP"] - data["BOLL_DOWN"] == 0,
            0.5,
            (data["单位净值"] - data["BOLL_DOWN"])
            / (data["BOLL_UP"] - data["BOLL_DOWN"]),
        )
        return data

    @staticmethod
    def calculate_weekly_kdj(
        data: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3
    ) -> pd.DataFrame:
        """计算基金周级别KDJ"""
        df = data.copy()

        # 对纯连续净值，计算当周的最高净值和最低净值
        df_sorted = df.sort_values("净值日期").set_index("净值日期")
        resampled = df_sorted.resample("W-FRI").agg(
            {"单位净值": ["max", "min", "last"]}
        ).dropna()

        # 展平列名
        resampled.columns = ["最高", "最低", "收盘"]

        low_list = resampled["最低"].rolling(window=n, min_periods=1).min()
        high_list = resampled["最高"].rolling(window=n, min_periods=1).max()

        rsv = (resampled["收盘"] - low_list) / (high_list - low_list) * 100
        # 防止除0
        rsv = rsv.fillna(50)

        resampled["KDJ_K_W"] = rsv.ewm(com=m1 - 1, adjust=False).mean()
        resampled["KDJ_D_W"] = resampled["KDJ_K_W"].ewm(com=m2 - 1, adjust=False).mean()
        resampled["KDJ_J_W"] = (
            3 * resampled["KDJ_K_W"] - 2 * resampled["KDJ_D_W"]
        )

        kdj_cols = resampled[["KDJ_K_W", "KDJ_D_W", "KDJ_J_W"]].reset_index()

        merged = pd.merge_asof(
            df.sort_values("净值日期"),
            kdj_cols.sort_values("净值日期"),
            left_on="净值日期",
            right_on="净值日期",
            direction="backward",
        )

        data["KDJ_K_W"] = merged["KDJ_K_W"]
        data["KDJ_D_W"] = merged["KDJ_D_W"]
        data["KDJ_J_W"] = merged["KDJ_J_W"]
        return data

    @staticmethod
    def calculate_monthly_kdj(
        data: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3
    ) -> pd.DataFrame:
        """计算基金月级别KDJ"""
        df = data.copy()

        df_sorted = df.sort_values("净值日期").set_index("净值日期")
        resampled = df_sorted.resample("ME").agg(
            {"单位净值": ["max", "min", "last"]}
        ).dropna()

        resampled.columns = ["最高", "最低", "收盘"]

        low_list = resampled["最低"].rolling(window=n, min_periods=1).min()
        high_list = resampled["最高"].rolling(window=n, min_periods=1).max()
        rsv = (resampled["收盘"] - low_list) / (high_list - low_list) * 100
        rsv = rsv.fillna(50)

        resampled["KDJ_K_M"] = rsv.ewm(com=m1 - 1, adjust=False).mean()
        resampled["KDJ_D_M"] = resampled["KDJ_K_M"].ewm(com=m2 - 1, adjust=False).mean()
        resampled["KDJ_J_M"] = (
            3 * resampled["KDJ_K_M"] - 2 * resampled["KDJ_D_M"]
        )

        kdj_cols = resampled[["KDJ_K_M", "KDJ_D_M", "KDJ_J_M"]].reset_index()

        merged = pd.merge_asof(
            df.sort_values("净值日期"),
            kdj_cols.sort_values("净值日期"),
            left_on="净值日期",
            right_on="净值日期",
            direction="backward",
        )

        data["KDJ_K_M"] = merged["KDJ_K_M"]
        data["KDJ_D_M"] = merged["KDJ_D_M"]
        data["KDJ_J_M"] = merged["KDJ_J_M"]
        return data

    @staticmethod
    def calculate_roc(data: pd.DataFrame, periods: list = [10, 20]) -> pd.DataFrame:
        """计算变动率指标 (Rate of Change)"""
        for period in periods:
            data[f"ROC{period}"] = data["单位净值"].pct_change(periods=period) * 100
        return data

    @staticmethod
    def calculate_mom(data: pd.DataFrame, periods: list = [10, 20]) -> pd.DataFrame:
        """计算动量指标 (Momentum)"""
        for period in periods:
            data[f"MOM{period}"] = data["单位净值"].diff(periods=period)
        return data

    def calculate_all(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算所有支持的技术指标"""
        # 确保按日期正序排列
        data = data.sort_values("净值日期").copy()

        data = self.calculate_ma(data)
        data = self.calculate_ema(data)
        data = self.calculate_rsi(data)
        data = self.calculate_macd(data)
        data = self.calculate_boll(data)
        data = self.calculate_roc(data)
        data = self.calculate_mom(data)
        data = self.calculate_weekly_kdj(data)
        data = self.calculate_monthly_kdj(data)

        # 截取保留2位小数
        float_cols = data.select_dtypes(include=["float64"]).columns
        data[float_cols] = data[float_cols].round(4)

        return data


def process_fund_indicators(
    input_dir: str, output_dir: str, fund_list_file: Optional[str] = None
):
    """批量处理基金的技术指标"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 如果提供了列表文件，只处理列表中的基金
    fund_codes_to_process = None
    if fund_list_file and os.path.exists(fund_list_file):
        try:
            df_list = pd.read_csv(fund_list_file, dtype={"fund_code": str})
            fund_codes_to_process = set(df_list["fund_code"].tolist())
        except Exception as e:
            logging.error(f"读取基金列表失败: {e}")

    files = [f for f in os.listdir(input_dir) if f.endswith("_nav.csv")]

    if fund_codes_to_process:
        files = [f for f in files if f.split("_")[0] in fund_codes_to_process]

    logging.info(f"找到 {len(files)} 个待计算的基金净值文件")

    calc = FundTechnicalIndicators()
    success_count = 0

    for file in tqdm(files, desc="计算基金技术指标"):
        fund_code = file.split("_")[0]
        input_path = os.path.join(input_dir, file)
        output_path = os.path.join(output_dir, f"{fund_code}_indicators.csv")

        try:
            df = pd.read_csv(input_path)

            if len(df) < 20:
                logging.warning(
                    f"基金 {fund_code} 的数据量太少 ({len(df)} 行)，跳过"
                )
                continue

            # 清理数据
            if "净值日期" not in df.columns:
                logging.warning(f"基金 {fund_code} 缺少净值日期列")
                continue

            df["净值日期"] = pd.to_datetime(df["净值日期"])
            df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")

            df = df.dropna(subset=["单位净值"]).copy()

            # 计算指标
            result_df = calc.calculate_all(df)

            result_df.to_csv(output_path, index=False)
            success_count += 1

        except Exception as e:
            logging.error(f"处理基金 {fund_code} 时出错: {e}")

    logging.info(f"完成！成功处理 {success_count}/{len(files)} 个基金")


def main():
    parser = argparse.ArgumentParser(description="综合计算公募基金的技术指标")
    parser.add_argument(
        "--input-dir",
        type=str,
        default="output/fund/details/nav",
        help="净值数据的输入目录",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/fund/indicators",
        help="技术指标的输出目录",
    )
    parser.add_argument(
        "--fund-list",
        type=str,
        default=None,
        help="可选：只处理该CSV列表中(fund_code列)的基金",
    )
    parser.add_argument(
        "--fund-code",
        type=str,
        default=None,
        help="可选：只处理指定的基金代码",
    )

    args = parser.parse_args()

    if args.fund_code:
        # 单独处理一个
        file_name = f"{args.fund_code}_nav.csv"
        input_file = os.path.join(args.input_dir, file_name)
        if not os.path.exists(input_file):
            logging.error(f"未找到基金 {args.fund_code} 的净值文件: {input_file}")
            return

        output_dir = args.output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        output_file = os.path.join(output_dir, f"{args.fund_code}_indicators.csv")

        calc = FundTechnicalIndicators()
        try:
            df = pd.read_csv(input_file)
            df["净值日期"] = pd.to_datetime(df["净值日期"])
            result_df = calc.calculate_all(df)
            result_df.to_csv(output_file, index=False)
            logging.info(
                f"成功保存 {args.fund_code} 的技术指标到 {output_file}"
            )
        except Exception as e:
            logging.error(f"处理出错: {e}")

    else:
        # 批量处理
        process_fund_indicators(args.input_dir, args.output_dir, args.fund_list)


if __name__ == "__main__":
    main()
