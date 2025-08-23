"""Compute technical indicators for ETF daily data.

Provides the TechnicalIndicators class with static methods for computing
MA, EMA, RSI, MACD, KDJ, Bollinger Bands, and many more. Also provides
ETFIndicatorCalculator for batch processing and get_etf_indicators_realtime
for live single-ETF indicator computation via akshare.

Usage:
    python -m src.data.etf.indicators --input-dir output/etf/details/nav --output-dir output/etf/indicators
    python -m src.data.etf.indicators --realtime --symbol sh510300 --output-dir output/etf/indicators
"""

import argparse
import datetime
import os
import re
import logging
from typing import Optional

import pandas as pd
import numpy as np
import akshare as ak
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class TechnicalIndicators:
    """Technical indicator calculator."""

    @staticmethod
    def calculate_ma(data: pd.DataFrame, periods: list = [5, 10, 20, 30, 60, 120, 250]) -> pd.DataFrame:
        """Calculate Moving Average."""
        for period in periods:
            data[f'MA{period}'] = data['收盘'].rolling(window=period).mean()
        return data

    @staticmethod
    def calculate_ema(data: pd.DataFrame, periods: list = [5, 10, 20, 30, 60, 120]) -> pd.DataFrame:
        """Calculate Exponential Moving Average."""
        for period in periods:
            data[f'EMA{period}'] = data['收盘'].ewm(span=period, adjust=False).mean()
        return data

    @staticmethod
    def calculate_rsi(data: pd.DataFrame, periods: list = [6, 12, 24]) -> pd.DataFrame:
        """Calculate Relative Strength Index."""
        for period in periods:
            delta = data['收盘'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            data[f'RSI{period}'] = 100 - (100 / (1 + rs))
        return data

    @staticmethod
    def calculate_macd(data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        """Calculate MACD (Moving Average Convergence Divergence)."""
        ema_fast = data['收盘'].ewm(span=fast, adjust=False).mean()
        ema_slow = data['收盘'].ewm(span=slow, adjust=False).mean()
        data['MACD_DIF'] = ema_fast - ema_slow
        data['MACD_DEA'] = data['MACD_DIF'].ewm(span=signal, adjust=False).mean()
        data['MACD_BAR'] = 2 * (data['MACD_DIF'] - data['MACD_DEA'])
        return data

    @staticmethod
    def calculate_kdj(data: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
        """Calculate KDJ (Stochastic) indicator."""
        low_list = data['最低'].rolling(window=n, min_periods=n).min()
        high_list = data['最高'].rolling(window=n, min_periods=n).max()
        rsv = (data['收盘'] - low_list) / (high_list - low_list) * 100

        data['KDJ_K'] = rsv.ewm(com=m1-1, adjust=False).mean()
        data['KDJ_D'] = data['KDJ_K'].ewm(com=m2-1, adjust=False).mean()
        data['KDJ_J'] = 3 * data['KDJ_K'] - 2 * data['KDJ_D']
        return data

    @staticmethod
    def calculate_weekly_kdj(data: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
        """Calculate weekly-level KDJ."""
        if '日期' not in data.columns:
            return data

        df = data.copy()
        df['日期'] = pd.to_datetime(df['日期'])
        df_sorted = df.sort_values('日期').set_index('日期')

        resampled = df_sorted.resample('W-FRI').agg({
            '开盘': 'first',
            '最高': 'max',
            '最低': 'min',
            '收盘': 'last'
        }).dropna()

        low_list = resampled['最低'].rolling(window=n, min_periods=1).min()
        high_list = resampled['最高'].rolling(window=n, min_periods=1).max()
        rsv = (resampled['收盘'] - low_list) / (high_list - low_list) * 100

        resampled['KDJ_K_W'] = rsv.ewm(com=m1-1, adjust=False).mean()
        resampled['KDJ_D_W'] = resampled['KDJ_K_W'].ewm(com=m2-1, adjust=False).mean()
        resampled['KDJ_J_W'] = 3 * resampled['KDJ_K_W'] - 2 * resampled['KDJ_D_W']

        kdj_cols = resampled[['KDJ_K_W', 'KDJ_D_W', 'KDJ_J_W']].reset_index()

        merged = pd.merge_asof(df.sort_values('日期'), kdj_cols.sort_values('日期'), on='日期', direction='backward')

        data['KDJ_K_W'] = merged['KDJ_K_W']
        data['KDJ_D_W'] = merged['KDJ_D_W']
        data['KDJ_J_W'] = merged['KDJ_J_W']
        return data

    @staticmethod
    def calculate_monthly_kdj(data: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
        """Calculate monthly-level KDJ."""
        if '日期' not in data.columns:
            return data

        df = data.copy()
        df['日期'] = pd.to_datetime(df['日期'])
        df_sorted = df.sort_values('日期').set_index('日期')

        resampled = df_sorted.resample('ME').agg({
            '开盘': 'first',
            '最高': 'max',
            '最低': 'min',
            '收盘': 'last'
        }).dropna()

        low_list = resampled['最低'].rolling(window=n, min_periods=1).min()
        high_list = resampled['最高'].rolling(window=n, min_periods=1).max()
        rsv = (resampled['收盘'] - low_list) / (high_list - low_list) * 100

        resampled['KDJ_K_M'] = rsv.ewm(com=m1-1, adjust=False).mean()
        resampled['KDJ_D_M'] = resampled['KDJ_K_M'].ewm(com=m2-1, adjust=False).mean()
        resampled['KDJ_J_M'] = 3 * resampled['KDJ_K_M'] - 2 * resampled['KDJ_D_M']

        kdj_cols = resampled[['KDJ_K_M', 'KDJ_D_M', 'KDJ_J_M']].reset_index()

        merged = pd.merge_asof(df.sort_values('日期'), kdj_cols.sort_values('日期'), on='日期', direction='backward')

        data['KDJ_K_M'] = merged['KDJ_K_M']
        data['KDJ_D_M'] = merged['KDJ_D_M']
        data['KDJ_J_M'] = merged['KDJ_J_M']
        return data

    @staticmethod
    def calculate_bollinger(data: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
        """Calculate Bollinger Bands."""
        data['BOLL_MID'] = data['收盘'].rolling(window=period).mean()
        rolling_std = data['收盘'].rolling(window=period).std()
        data['BOLL_UP'] = data['BOLL_MID'] + (rolling_std * num_std)
        data['BOLL_DOWN'] = data['BOLL_MID'] - (rolling_std * num_std)
        data['BOLL_WIDTH'] = (data['BOLL_UP'] - data['BOLL_DOWN']) / data['BOLL_MID']
        data['BOLL_PERCENT'] = (data['收盘'] - data['BOLL_DOWN']) / (data['BOLL_UP'] - data['BOLL_DOWN'])
        return data

    @staticmethod
    def calculate_volume_ratio(data: pd.DataFrame, period: int = 5) -> pd.DataFrame:
        """Calculate Volume Ratio."""
        data['量比'] = data['成交量'] / data['成交量'].rolling(window=period).mean()
        return data

    @staticmethod
    def calculate_turnover_rate(data: pd.DataFrame, shares_outstanding: Optional[float] = None) -> pd.DataFrame:
        """Calculate Turnover Rate.

        If shares_outstanding is provided, uses it directly; otherwise estimates
        from volume and price.
        """
        if shares_outstanding and shares_outstanding > 0:
            data['换手率'] = (data['成交量'] / shares_outstanding) * 100
        else:
            data['换手率_估算'] = data['成交额'] / (data['收盘'] * data['成交量'])
        return data

    @staticmethod
    def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Average True Range."""
        high_low = data['最高'] - data['最低']
        high_close = np.abs(data['最高'] - data['收盘'].shift())
        low_close = np.abs(data['最低'] - data['收盘'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        data['ATR'] = true_range.rolling(window=period).mean()
        data['ATR_PERCENT'] = data['ATR'] / data['收盘'] * 100
        return data

    @staticmethod
    def calculate_cci(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Commodity Channel Index."""
        tp = (data['最高'] + data['最低'] + data['收盘']) / 3
        sma_tp = tp.rolling(window=period).mean()
        mean_dev = tp.rolling(window=period).apply(lambda x: np.mean(np.abs(x - x.mean())))
        data['CCI'] = (tp - sma_tp) / (0.015 * mean_dev)
        return data

    @staticmethod
    def calculate_williams_r(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Williams %R."""
        highest_high = data['最高'].rolling(window=period).max()
        lowest_low = data['最低'].rolling(window=period).min()
        data['WR'] = (highest_high - data['收盘']) / (highest_high - lowest_low) * -100
        return data

    @staticmethod
    def calculate_stochastic(data: pd.DataFrame, fastk_period: int = 14, slowk_period: int = 3, slowd_period: int = 3) -> pd.DataFrame:
        """Calculate Stochastic Oscillator."""
        lowest_low = data['最低'].rolling(window=fastk_period).min()
        highest_high = data['最高'].rolling(window=fastk_period).max()
        fastk = (data['收盘'] - lowest_low) / (highest_high - lowest_low) * 100
        data['STOCH_K'] = fastk.rolling(window=slowk_period).mean()
        data['STOCH_D'] = data['STOCH_K'].rolling(window=slowd_period).mean()
        return data

    @staticmethod
    def calculate_obv(data: pd.DataFrame) -> pd.DataFrame:
        """Calculate On Balance Volume."""
        obv = [0]
        for i in range(1, len(data)):
            if data['收盘'].iloc[i] > data['收盘'].iloc[i-1]:
                obv.append(obv[-1] + data['成交量'].iloc[i])
            elif data['收盘'].iloc[i] < data['收盘'].iloc[i-1]:
                obv.append(obv[-1] - data['成交量'].iloc[i])
            else:
                obv.append(obv[-1])
        data['OBV'] = obv
        data['OBV_MA'] = data['OBV'].rolling(window=20).mean()
        return data

    @staticmethod
    def calculate_mfi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Money Flow Index."""
        typical_price = (data['最高'] + data['最低'] + data['收盘']) / 3
        money_flow = typical_price * data['成交量']
        positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0)
        negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0)
        positive_sum = positive_flow.rolling(window=period).sum()
        negative_sum = negative_flow.rolling(window=period).sum()
        mfi = 100 - (100 / (1 + positive_sum / negative_sum))
        data['MFI'] = mfi
        return data

    @staticmethod
    def calculate_adx(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Average Directional Index."""
        plus_dm = data['最高'].diff()
        minus_dm = data['最低'].diff().abs() * -1
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr1 = data['最高'] - data['最低']
        tr2 = abs(data['最高'] - data['收盘'].shift(1))
        tr3 = abs(data['最低'] - data['收盘'].shift(1))
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = true_range.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        data['ADX'] = dx.rolling(window=period).mean()
        data['PLUS_DI'] = plus_di
        data['MINUS_DI'] = minus_di
        return data

    @staticmethod
    def calculate_pvt(data: pd.DataFrame) -> pd.DataFrame:
        """Calculate Price Volume Trend."""
        pct_change = data['收盘'].pct_change()
        data['PVT'] = (pct_change * data['成交量']).cumsum()
        return data

    @staticmethod
    def calculate_vwap(data: pd.DataFrame) -> pd.DataFrame:
        """Calculate Volume Weighted Average Price."""
        typical_price = (data['最高'] + data['最低'] + data['收盘']) / 3
        data['VWAP'] = (typical_price * data['成交量']).cumsum() / data['成交量'].cumsum()
        return data

    @staticmethod
    def calculate_roc(data: pd.DataFrame, periods: list = [10, 20]) -> pd.DataFrame:
        """Calculate Rate of Change."""
        for period in periods:
            data[f'ROC{period}'] = ((data['收盘'] - data['收盘'].shift(period)) / data['收盘'].shift(period)) * 100
        return data

    @staticmethod
    def calculate_momentum(data: pd.DataFrame, periods: list = [10, 20]) -> pd.DataFrame:
        """Calculate Momentum."""
        for period in periods:
            data[f'MOM{period}'] = data['收盘'] - data['收盘'].shift(period)
        return data

    @staticmethod
    def calculate_dmi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Directional Movement Index."""
        plus_dm = data['最高'].diff()
        minus_dm = data['最低'].diff() * -1
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        tr1 = data['最高'] - data['最低']
        tr2 = abs(data['最高'] - data['收盘'].shift(1))
        tr3 = abs(data['最低'] - data['收盘'].shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()
        data['PDI'] = 100 * plus_dm.rolling(window=period).mean() / atr
        data['MDI'] = 100 * minus_dm.rolling(window=period).mean() / atr
        data['ADX_DMI'] = abs(data['PDI'] - data['MDI']) / (data['PDI'] + data['MDI']) * 100
        return data

    @staticmethod
    def calculate_psy(data: pd.DataFrame, period: int = 12) -> pd.DataFrame:
        """Calculate Psychological Line."""
        price_change = data['收盘'].diff()
        up_days = (price_change > 0).rolling(window=period).sum()
        data['PSY'] = up_days / period * 100
        return data

    @staticmethod
    def calculate_arbr(data: pd.DataFrame, period: int = 26) -> pd.DataFrame:
        """Calculate ARBR (Sentiment indicators)."""
        ar_up = data['最高'] - data['开盘']
        ar_down = data['开盘'] - data['最低']
        data['AR'] = ar_up.rolling(window=period).sum() / ar_down.rolling(window=period).sum() * 100

        br_up = data['最高'] - data['收盘'].shift(1)
        br_down = data['收盘'].shift(1) - data['最低']
        data['BR'] = br_up.rolling(window=period).sum() / br_down.rolling(window=period).sum() * 100
        return data

    @staticmethod
    def calculate_cmo(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate Chande Momentum Oscillator."""
        diff = data['收盘'].diff()
        sum_gains = diff.where(diff > 0, 0).rolling(window=period).sum()
        sum_losses = abs(diff.where(diff < 0, 0)).rolling(window=period).sum()
        data['CMO'] = ((sum_gains - sum_losses) / (sum_gains + sum_losses)) * 100
        return data

    @staticmethod
    def calculate_trix(data: pd.DataFrame, period: int = 15) -> pd.DataFrame:
        """Calculate Triple Exponential Moving Average."""
        ema1 = data['收盘'].ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        ema3 = ema2.ewm(span=period, adjust=False).mean()
        data['TRIX'] = (ema3 - ema3.shift(1)) / ema3.shift(1) * 100
        return data

    @staticmethod
    def calculate_sar(data: pd.DataFrame, acceleration: float = 0.02, maximum: float = 0.2) -> pd.DataFrame:
        """Calculate Parabolic SAR."""
        high = data['最高']
        low = data['最低']
        close = data['收盘']

        sar = close.copy()
        af = acceleration
        ep = high.iloc[0]
        trend = 1  # 1 for uptrend, -1 for downtrend

        sar_values = []
        for i in range(len(data)):
            if i == 0:
                sar_values.append(sar.iloc[i])
                continue

            sar_values.append(sar.iloc[i-1] + af * (ep - sar.iloc[i-1]))

            if trend == 1:
                if low.iloc[i] < sar_values[-1]:
                    trend = -1
                    sar_values[-1] = ep
                    ep = low.iloc[i]
                    af = acceleration
                else:
                    if high.iloc[i] > ep:
                        ep = high.iloc[i]
                        af = min(af + acceleration, maximum)
            else:
                if high.iloc[i] > sar_values[-1]:
                    trend = 1
                    sar_values[-1] = ep
                    ep = high.iloc[i]
                    af = acceleration
                else:
                    if low.iloc[i] < ep:
                        ep = low.iloc[i]
                        af = min(af + acceleration, maximum)

        data['SAR'] = sar_values
        data['SAR_TREND'] = trend
        return data

    @staticmethod
    def calculate_dpo(data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Calculate Detrended Price Oscillator."""
        sma = data['收盘'].rolling(window=period).mean()
        data['DPO'] = data['收盘'].shift(int(period/2) + 1) - sma
        return data

    @staticmethod
    def calculate_vr(data: pd.DataFrame, period: int = 26) -> pd.DataFrame:
        """Calculate Volume Ratio."""
        close_diff = data['收盘'].diff()
        av = data['成交量'].where(close_diff > 0, 0).rolling(window=period).sum()
        bv = data['成交量'].where(close_diff < 0, 0).rolling(window=period).sum()
        cv = data['成交量'].where(close_diff == 0, 0).rolling(window=period).sum()
        data['VR'] = (av + cv/2) / (bv + cv/2) * 100
        return data

    @staticmethod
    def calculate_cr(data: pd.DataFrame, period: int = 26) -> pd.DataFrame:
        """Calculate CR energy indicator."""
        mid = (data['最高'] + data['最低']) / 2
        up = data['最高'] - mid.shift(1)
        down = mid.shift(1) - data['最低']
        data['CR'] = up.rolling(window=period).sum() / down.rolling(window=period).sum() * 100
        return data


class ETFIndicatorCalculator:
    """Batch ETF technical indicator calculator."""

    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.indicators = TechnicalIndicators()
        os.makedirs(output_dir, exist_ok=True)

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all technical indicators on a DataFrame."""
        df = df.copy()

        column_mapping = {
            'close': '收盘',
            'open': '开盘',
            'high': '最高',
            'low': '最低',
            'volume': '成交量',
            'amount': '成交额',
        }
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

        # Basic
        df = self.indicators.calculate_ma(df)
        df = self.indicators.calculate_ema(df)

        # Momentum
        df = self.indicators.calculate_rsi(df)
        df = self.indicators.calculate_macd(df)
        df = self.indicators.calculate_kdj(df)
        df = self.indicators.calculate_weekly_kdj(df)
        df = self.indicators.calculate_monthly_kdj(df)
        df = self.indicators.calculate_cci(df)
        df = self.indicators.calculate_williams_r(df)
        df = self.indicators.calculate_stochastic(df)
        df = self.indicators.calculate_roc(df)
        df = self.indicators.calculate_momentum(df)
        df = self.indicators.calculate_cmo(df)
        df = self.indicators.calculate_trix(df)
        df = self.indicators.calculate_dpo(df)

        # Volatility
        df = self.indicators.calculate_bollinger(df)
        df = self.indicators.calculate_atr(df)
        df = self.indicators.calculate_adx(df)

        # Volume
        df = self.indicators.calculate_volume_ratio(df)
        df = self.indicators.calculate_obv(df)
        df = self.indicators.calculate_mfi(df)
        df = self.indicators.calculate_pvt(df)
        df = self.indicators.calculate_vwap(df)
        df = self.indicators.calculate_vr(df)
        df = self.indicators.calculate_cr(df)

        # Trend
        df = self.indicators.calculate_dmi(df)
        df = self.indicators.calculate_psy(df)
        df = self.indicators.calculate_arbr(df)
        df = self.indicators.calculate_sar(df)

        # Turnover (estimated)
        df = self.indicators.calculate_turnover_rate(df)

        return df

    def process_single_etf(self, file_path: str) -> Optional[pd.DataFrame]:
        """Process a single ETF CSV file."""
        try:
            df = pd.read_csv(file_path)
            if df.empty:
                logging.warning(f"File is empty: {file_path}")
                return None

            df = self.calculate_all_indicators(df)
            return df
        except Exception as e:
            logging.error(f"Failed to process {file_path}: {e}")
            return None

    def process_all_etfs(self, etf_list_path: Optional[str] = None):
        """Process all ETF files in the input directory."""
        if etf_list_path and os.path.exists(etf_list_path):
            df_etf = pd.read_csv(etf_list_path)
            etf_codes = df_etf['代码'].tolist()
        else:
            etf_codes = [f.replace('_nav.csv', '') for f in os.listdir(self.input_dir) if f.endswith('_nav.csv')]

        success_count = 0
        fail_count = 0
        skip_count = 0

        for code in tqdm(etf_codes, desc="Computing ETF indicators"):
            code = code.strip().lower()
            input_file = os.path.join(self.input_dir, f"{code}_nav.csv")
            output_file = os.path.join(self.output_dir, f"{code}_indicators.csv")

            if os.path.exists(output_file):
                skip_count += 1
                continue

            if not os.path.exists(input_file):
                logging.warning(f"Input file not found: {input_file}")
                fail_count += 1
                continue

            df = self.process_single_etf(input_file)
            if df is not None:
                df.to_csv(output_file, index=False, encoding='utf-8-sig')
                success_count += 1
            else:
                fail_count += 1

        logging.info(
            f"Indicator computation done! success={success_count}, skipped={skip_count}, failed={fail_count}"
        )


def get_etf_indicators_realtime(symbol: str, period: str = "daily") -> pd.DataFrame:
    """Fetch ETF data from akshare and compute all indicators in one go.

    Args:
        symbol: ETF symbol (e.g. 'sh510300' or '510300').
        period: Data frequency ('daily', 'weekly', 'monthly').

    Returns:
        DataFrame with price data and all computed indicators.
    """
    try:
        symbol_clean = re.sub(r'\D', '', symbol).zfill(6)

        df = ak.fund_etf_hist_em(
            symbol=symbol_clean,
            period=period,
            adjust="qfq",
        )

        if df is None or df.empty:
            logging.error(f"Cannot fetch ETF data: {symbol}")
            return pd.DataFrame()

        calculator = TechnicalIndicators()

        df = df.rename(columns={
            '日期': 'date',
            '开盘': '开盘',
            '收盘': '收盘',
            '最高': '最高',
            '最低': '最低',
            '成交量': '成交量',
            '成交额': '成交额',
            '振幅': '振幅',
            '涨跌幅': '涨跌幅',
            '涨跌额': '涨跌额',
            '换手率': '换手率',
        })

        df = calculator.calculate_ma(df)
        df = calculator.calculate_ema(df)
        df = calculator.calculate_rsi(df)
        df = calculator.calculate_macd(df)
        df = calculator.calculate_kdj(df)
        df = calculator.calculate_weekly_kdj(df)
        df = calculator.calculate_monthly_kdj(df)
        df = calculator.calculate_bollinger(df)
        df = calculator.calculate_volume_ratio(df)
        df = calculator.calculate_atr(df)
        df = calculator.calculate_cci(df)
        df = calculator.calculate_williams_r(df)
        df = calculator.calculate_stochastic(df)
        df = calculator.calculate_obv(df)
        df = calculator.calculate_mfi(df)
        df = calculator.calculate_pvt(df)
        df = calculator.calculate_vwap(df)
        df = calculator.calculate_roc(df)
        df = calculator.calculate_momentum(df)
        df = calculator.calculate_dmi(df)
        df = calculator.calculate_psy(df)
        df = calculator.calculate_arbr(df)
        df = calculator.calculate_cmo(df)
        df = calculator.calculate_trix(df)
        df = calculator.calculate_vr(df)
        df = calculator.calculate_cr(df)
        df = calculator.calculate_dpo(df)

        return df

    except Exception as e:
        logging.error(f"Failed to compute ETF indicators {symbol}: {e}")
        return pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(description="Compute ETF technical indicators")
    parser.add_argument(
        "--input-dir",
        type=str,
        default="output/etf/details/nav",
        help="ETF historical data directory",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/etf/indicators",
        help="Indicator output directory",
    )
    parser.add_argument(
        "--etf-list",
        type=str,
        default="output/etf/lists/all_etfs_akshare.csv",
        help="ETF list CSV path",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="",
        help="Single ETF symbol (e.g. sh510300) for realtime mode",
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Realtime mode: fetch from akshare and compute indicators",
    )
    args = parser.parse_args()

    if args.realtime and args.symbol:
        df = get_etf_indicators_realtime(args.symbol)
        if not df.empty:
            output_file = os.path.join(args.output_dir, f"{args.symbol}_indicators.csv")
            os.makedirs(args.output_dir, exist_ok=True)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            logging.info(f"Saved to: {output_file}")
            print("\nLatest indicator values:")
            print(df.iloc[-1][['date', '收盘', 'MA5', 'MA20', 'RSI6', 'RSI12', 'MACD_DIF', 'MACD_DEA',
                              'KDJ_K', 'KDJ_D', 'KDJ_J', '量比', 'BOLL_UP', 'BOLL_DOWN']].to_string())
    else:
        calculator = ETFIndicatorCalculator(args.input_dir, args.output_dir)
        calculator.process_all_etfs(args.etf_list)


if __name__ == "__main__":
    main()

# Updated: 2025-08-23
