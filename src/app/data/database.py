"""SQLite 数据库操作 — 交易记录、持仓、决策、复盘、收件人管理。

表结构：
    - trades:     交易记录
    - positions:  持仓快照
    - decisions:  决策记录
    - reviews:    复盘笔记
    - recipients: 邮件收件人
    - email_logs: 邮件发送记录
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


class Database:
    """SQLite 数据库操作封装。

    Attributes:
        db_path: 数据库文件路径。
    """

    # 表创建语句
    _SCHEMA: list[str] = [
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT,
            symbol TEXT NOT NULL,
            name TEXT,
            asset_type TEXT,
            direction TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            amount REAL,
            commission REAL DEFAULT 0,
            tax REAL DEFAULT 0,
            decision_id INTEGER,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT,
            quantity INTEGER,
            avg_cost REAL,
            market_price REAL,
            market_value REAL,
            pnl REAL,
            pnl_pct REAL,
            UNIQUE(date, symbol)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal TEXT,
            confidence REAL,
            reasons TEXT,
            agent_analysis TEXT,
            outcome TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            title TEXT,
            category TEXT,
            content TEXT,
            lessons TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            is_active INTEGER DEFAULT 1,
            notify_signals INTEGER DEFAULT 1,
            notify_trades INTEGER DEFAULT 1,
            notify_reports INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time TEXT,
            recipient_id INTEGER,
            recipient_email TEXT,
            subject TEXT,
            email_type TEXT,
            status TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """,
    ]

    def __init__(self, db_path: str | Path = "data/finlab.db") -> None:
        """初始化数据库连接并确保表结构存在。

        Args:
            db_path: SQLite 数据库文件路径。
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接。"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        """创建所有表（如不存在）。"""
        with self._get_conn() as conn:
            for ddl in self._SCHEMA:
                conn.execute(ddl)

    # ------------------------------------------------------------------
    # trades — 交易记录
    # ------------------------------------------------------------------

    def insert_trade(self, trade: dict) -> int:
        """插入一条交易记录。

        Args:
            trade: 交易数据字典，键对应 trades 表字段。

        Returns:
            新插入记录的 ID。
        """
        keys = [
            "date", "time", "symbol", "name", "asset_type",
            "direction", "price", "quantity", "amount",
            "commission", "tax", "decision_id", "notes",
        ]
        values = {k: trade.get(k) for k in keys}
        columns = ", ".join(k for k, v in values.items() if v is not None)
        placeholders = ", ".join(f":{k}" for k, v in values.items() if v is not None)
        filtered = {k: v for k, v in values.items() if v is not None}

        sql = f"INSERT INTO trades ({columns}) VALUES ({placeholders})"
        with self._get_conn() as conn:
            cursor = conn.execute(sql, filtered)
            return cursor.lastrowid  # type: ignore[return-value]

    def get_trades(
        self,
        symbol: str | None = None,
        direction: str | None = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        """查询交易记录。

        Args:
            symbol: 按资产代码筛选。
            direction: 按方向筛选 (买入/卖出)。
            limit: 最大返回条数。

        Returns:
            交易记录 DataFrame。
        """
        sql = "SELECT * FROM trades WHERE 1=1"
        params: list = []

        if symbol:
            sql += " AND symbol LIKE ?"
            params.append(f"%{symbol}%")
        if direction:
            sql += " AND direction = ?"
            params.append(direction)

        sql += " ORDER BY date DESC, time DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ------------------------------------------------------------------
    # positions — 持仓快照
    # ------------------------------------------------------------------

    def upsert_position(self, position: dict) -> None:
        """插入或更新持仓快照（按 date+symbol 去重）。

        Args:
            position: 持仓数据字典。
        """
        sql = """
            INSERT INTO positions (date, symbol, name, quantity, avg_cost,
                                   market_price, market_value, pnl, pnl_pct)
            VALUES (:date, :symbol, :name, :quantity, :avg_cost,
                    :market_price, :market_value, :pnl, :pnl_pct)
            ON CONFLICT(date, symbol) DO UPDATE SET
                name=excluded.name,
                quantity=excluded.quantity,
                avg_cost=excluded.avg_cost,
                market_price=excluded.market_price,
                market_value=excluded.market_value,
                pnl=excluded.pnl,
                pnl_pct=excluded.pnl_pct
        """
        with self._get_conn() as conn:
            conn.execute(sql, position)

    def get_positions(self, date: str | None = None) -> pd.DataFrame:
        """获取持仓快照。

        Args:
            date: 指定日期，为 None 时取最新。

        Returns:
            持仓 DataFrame。
        """
        if date is None:
            sql = "SELECT * FROM positions WHERE date = (SELECT MAX(date) FROM positions)"
        else:
            sql = "SELECT * FROM positions WHERE date = ?"

        with self._get_conn() as conn:
            if date is None:
                return pd.read_sql_query(sql, conn)
            return pd.read_sql_query(sql, conn, params=[date])

    # ------------------------------------------------------------------
    # decisions — 决策记录
    # ------------------------------------------------------------------

    def insert_decision(self, decision: dict) -> int:
        """插入一条决策记录。

        Args:
            decision: 决策数据字典。

        Returns:
            新插入记录的 ID。
        """
        keys = [
            "date", "symbol", "signal", "confidence",
            "reasons", "agent_analysis", "outcome",
        ]
        values = {k: decision.get(k) for k in keys}
        columns = ", ".join(k for k, v in values.items() if v is not None)
        placeholders = ", ".join(f":{k}" for k, v in values.items() if v is not None)
        filtered = {k: v for k, v in values.items() if v is not None}

        sql = f"INSERT INTO decisions ({columns}) VALUES ({placeholders})"
        with self._get_conn() as conn:
            cursor = conn.execute(sql, filtered)
            return cursor.lastrowid  # type: ignore[return-value]

    def get_decisions(self, date: str | None = None, limit: int = 50) -> pd.DataFrame:
        """查询决策记录。

        Args:
            date: 按日期筛选。
            limit: 最大返回条数。

        Returns:
            决策记录 DataFrame。
        """
        if date:
            sql = "SELECT * FROM decisions WHERE date = ? ORDER BY created_at DESC LIMIT ?"
            params: list = [date, limit]
        else:
            sql = "SELECT * FROM decisions ORDER BY date DESC, created_at DESC LIMIT ?"
            params = [limit]

        with self._get_conn() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ------------------------------------------------------------------
    # reviews — 复盘笔记
    # ------------------------------------------------------------------

    def insert_review(self, review: dict) -> int:
        """插入一条复盘笔记。

        Args:
            review: 复盘数据字典。

        Returns:
            新插入记录的 ID。
        """
        keys = ["date", "title", "category", "content", "lessons"]
        values = {k: review.get(k) for k in keys}
        columns = ", ".join(k for k, v in values.items() if v is not None)
        placeholders = ", ".join(f":{k}" for k, v in values.items() if v is not None)
        filtered = {k: v for k, v in values.items() if v is not None}

        sql = f"INSERT INTO reviews ({columns}) VALUES ({placeholders})"
        with self._get_conn() as conn:
            cursor = conn.execute(sql, filtered)
            return cursor.lastrowid  # type: ignore[return-value]

    def get_reviews(self, category: str | None = None, limit: int = 50) -> pd.DataFrame:
        """查询复盘笔记。

        Args:
            category: 按类型筛选 (交易复盘/周复盘/月复盘)。
            limit: 最大返回条数。

        Returns:
            复盘笔记 DataFrame。
        """
        if category:
            sql = "SELECT * FROM reviews WHERE category = ? ORDER BY date DESC LIMIT ?"
            params: list = [category, limit]
        else:
            sql = "SELECT * FROM reviews ORDER BY date DESC LIMIT ?"
            params = [limit]

        with self._get_conn() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ------------------------------------------------------------------
    # recipients — 收件人管理
    # ------------------------------------------------------------------

    def insert_recipient(self, recipient: dict) -> int:
        """添加收件人。

        Args:
            recipient: 收件人数据字典。

        Returns:
            新插入记录的 ID。

        Raises:
            sqlite3.IntegrityError: 邮箱已存在。
        """
        keys = [
            "name", "email", "is_active",
            "notify_signals", "notify_trades", "notify_reports",
        ]
        values = {k: recipient.get(k) for k in keys}
        columns = ", ".join(k for k, v in values.items() if v is not None)
        placeholders = ", ".join(f":{k}" for k, v in values.items() if v is not None)
        filtered = {k: v for k, v in values.items() if v is not None}

        sql = f"INSERT INTO recipients ({columns}) VALUES ({placeholders})"
        with self._get_conn() as conn:
            cursor = conn.execute(sql, filtered)
            return cursor.lastrowid  # type: ignore[return-value]

    def get_recipients(self, active_only: bool = False) -> pd.DataFrame:
        """获取收件人列表。

        Args:
            active_only: 是否只返回启用的收件人。

        Returns:
            收件人 DataFrame。
        """
        if active_only:
            sql = "SELECT * FROM recipients WHERE is_active = 1 ORDER BY name"
        else:
            sql = "SELECT * FROM recipients ORDER BY name"

        with self._get_conn() as conn:
            return pd.read_sql_query(sql, conn)

    def update_recipient(self, recipient_id: int, updates: dict) -> None:
        """更新收件人信息。

        Args:
            recipient_id: 收件人 ID。
            updates: 要更新的字段字典。
        """
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["id"] = recipient_id
        sql = f"UPDATE recipients SET {set_clause} WHERE id = :id"
        with self._get_conn() as conn:
            conn.execute(sql, updates)

    def delete_recipient(self, recipient_id: int) -> None:
        """删除收件人。

        Args:
            recipient_id: 收件人 ID。
        """
        with self._get_conn() as conn:
            conn.execute("DELETE FROM recipients WHERE id = ?", (recipient_id,))

    # ------------------------------------------------------------------
    # email_logs — 邮件发送记录
    # ------------------------------------------------------------------

    def insert_email_log(self, log: dict) -> int:
        """记录一封邮件发送日志。

        Args:
            log: 日志数据字典。

        Returns:
            新插入记录的 ID。
        """
        keys = [
            "date", "time", "recipient_id", "recipient_email",
            "subject", "email_type", "status", "error_message",
        ]
        values = {k: log.get(k) for k in keys}
        columns = ", ".join(k for k, v in values.items() if v is not None)
        placeholders = ", ".join(f":{k}" for k, v in values.items() if v is not None)
        filtered = {k: v for k, v in values.items() if v is not None}

        sql = f"INSERT INTO email_logs ({columns}) VALUES ({placeholders})"
        with self._get_conn() as conn:
            cursor = conn.execute(sql, filtered)
            return cursor.lastrowid  # type: ignore[return-value]

    def get_email_logs(self, limit: int = 100) -> pd.DataFrame:
        """获取邮件发送记录。

        Args:
            limit: 最大返回条数。

        Returns:
            邮件日志 DataFrame。
        """
        sql = "SELECT * FROM email_logs ORDER BY date DESC, time DESC LIMIT ?"
        with self._get_conn() as conn:
            return pd.read_sql_query(sql, conn, params=[limit])

# Updated: 2025-01-21

# Updated: 2025-07-17
