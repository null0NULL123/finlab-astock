"""申万二级行业工具函数

提供读取日度指标、计算收益率、透视线阵、提取相关矩阵等公共功能。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 必需的列名
REQUIRED_DAILY_COLS = {"行业代码", "行业名称", "日期"}


def read_daily_metrics(path: Path) -> pd.DataFrame:
    """读取行业日度指标数据

    Args:
        path: CSV 文件路径

    Returns:
        处理后的 DataFrame
    """
    df = pd.read_csv(path, dtype={"行业代码": str}, encoding="utf-8-sig")
    missing = REQUIRED_DAILY_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

    df = df.copy()
    df["行业代码"] = df["行业代码"].astype(str)
    df["行业名称"] = df["行业名称"].astype(str)
    if "上级行业" in df.columns:
        df["上级行业"] = df["上级行业"].astype(str)
    else:
        df["上级行业"] = ""

    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
    df = df.dropna(subset=["日期"]).copy()
    return df


def apply_date_parent_filters(
    df: pd.DataFrame,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    parent: Optional[str] = None,
) -> pd.DataFrame:
    """应用日期和父行业过滤器

    Args:
        df: 输入 DataFrame
        start: 开始日期
        end: 结束日期
        parent: 上级行业名称

    Returns:
        过滤后的 DataFrame
    """
    out = df

    if parent is not None:
        out = out.loc[out["上级行业"].astype(str) == str(parent)].copy()

    if start is not None:
        out = out.loc[out["日期"] >= pd.to_datetime(start)].copy()
    if end is not None:
        out = out.loc[out["日期"] <= pd.to_datetime(end)].copy()

    return out


def compute_returns(
    df: pd.DataFrame,
    return_source: str = "pct",
) -> pd.DataFrame:
    """计算收益率

    Args:
        df: 包含行业代码、日期、涨跌幅或收盘指数的 DataFrame
        return_source: 'pct' 使用涨跌幅列，'close' 使用收盘指数计算

    Returns:
        添加了 'return' 列的 DataFrame
    """
    df = df.copy()

    if return_source == "pct":
        if "涨跌幅" not in df.columns:
            raise ValueError("缺少 '涨跌幅' 列")
        df["return"] = pd.to_numeric(df["涨跌幅"], errors="coerce") / 100.0
    elif return_source == "close":
        if "收盘指数" not in df.columns:
            raise ValueError("缺少 '收盘指数' 列")
        df["收盘指数"] = pd.to_numeric(df["收盘指数"], errors="coerce")
        df["return"] = df.groupby("行业代码")["收盘指数"].pct_change()
    else:
        raise ValueError(f"Unknown return source: {return_source}")

    return df


def pivot_returns(df_ret: pd.DataFrame) -> pd.DataFrame:
    """将长格式收益率数据透视为行业x日期矩阵

    Args:
        df_ret: 包含行业代码、日期、return 列的 DataFrame

    Returns:
        行业x日期的收益率矩阵
    """
    pivot = df_ret.pivot_table(
        index="行业代码",
        columns="日期",
        values="return",
        aggfunc="first",
    )
    return pivot


def compute_corr_matrix(
    pivot: pd.DataFrame,
    method: str = "pearson",
    min_periods: int = 30,
) -> pd.DataFrame:
    """计算相关矩阵

    Args:
        pivot: 行业x日期的收益率矩阵
        method: 相关系数计算方法
        min_periods: 最小观测期数

    Returns:
        行业x行业的相关矩阵
    """
    return pivot.T.corr(method=method, min_periods=min_periods)


def load_square_matrix(path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """加载行业x行业的方阵 CSV

    Args:
        path: 方阵 CSV 文件路径

    Returns:
        (矩阵 DataFrame, 行业代码到名称的映射)
    """
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")

    # 第一列是行业代码
    code_col = df.columns[0]
    df[code_col] = df[code_col].astype(str)
    df = df.set_index(code_col)

    # 第二列可能是行业名称
    name_map = {}
    if "行业名称" in df.columns:
        name_map = df["行业名称"].to_dict()
        df = df.drop(columns=["行业名称"])

    # 转换为数值
    df = df.apply(pd.to_numeric, errors="coerce")

    # 确保行列对齐
    common = df.index.intersection(df.columns)
    df = df.loc[common, common]

    return df, name_map


def extract_top_pairs(
    matrix: pd.DataFrame,
    k: int = 200,
    kind: str = "positive",
) -> pd.DataFrame:
    """提取相关矩阵中的 Top-K 行业对

    Args:
        matrix: 相关矩阵
        k: 提取数量
        kind: 'positive' 正相关, 'negative' 负相关, 'absolute' 绝对值

    Returns:
        包含行业对和相关系数的 DataFrame
    """
    # 提取上三角矩阵
    mask = np.triu(np.ones_like(matrix, dtype=bool), k=1)
    upper = matrix.where(mask)

    # 转换为长格式（先重置 index name 以避免冲突）
    upper = upper.rename_axis("industry_1", axis=0).rename_axis("industry_2", axis=1)
    pairs = upper.stack().reset_index()
    pairs.columns = ["industry_1", "industry_2", "correlation"]

    # 根据类型排序
    if kind == "positive":
        pairs = pairs.nlargest(k, "correlation")
    elif kind == "negative":
        pairs = pairs.nsmallest(k, "correlation")
    elif kind == "absolute":
        pairs["abs_corr"] = pairs["correlation"].abs()
        pairs = pairs.nlargest(k, "abs_corr")
        pairs = pairs.drop(columns=["abs_corr"])

    return pairs.reset_index(drop=True)


def write_cluster_summary(
    mapping: pd.DataFrame,
    summary_path: Path,
) -> None:
    """写入聚类摘要文件

    Args:
        mapping: 包含 industry_code, industry_name, cluster 列的 DataFrame
        summary_path: 输出文件路径
    """
    lines = []
    lines.append(f"Total industries: {mapping.shape[0]}")
    lines.append(f"Total clusters: {mapping['cluster'].nunique()}")
    lines.append("")

    sizes = (
        mapping.groupby("cluster")["industry_code"].size().sort_values(ascending=False)
    )

    for cluster_id in sizes.index.tolist():
        part = mapping.loc[mapping["cluster"] == cluster_id]
        part = part.sort_values(["industry_code"], kind="stable")
        lines.append(f"[Cluster {int(cluster_id)}] size={part.shape[0]}")
        for _, r in part.iterrows():
            lines.append(f"  - {r['industry_code']} {r['industry_name']}")
        lines.append("")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")

