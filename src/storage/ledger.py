"""
SQLite ledger for auditability and trade history.
"""
import sqlite3
import json
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import asdict

from src.strategy.signal_engine import TradeSignal, SignalDecision


class Ledger:
    """
    SQLite-based ledger for storing opportunities, orders, fills, and tradesets.
    Provides full audit trail for all trading activity.
    """

    def __init__(self, db_path: str = "arb_ledger.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Initialize database connection and create tables."""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        """Create all required tables if they don't exist."""
        cursor = self._conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                yes_ask REAL,
                no_ask REAL,
                yes_size REAL,
                no_size REAL,
                sum_cost REAL,
                edge REAL,
                cost_buffer REAL,
                decision TEXT NOT NULL,
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                tradeset_id INTEGER,
                market_id TEXT NOT NULL,
                token_id TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                price REAL NOT NULL,
                size REAL NOT NULL,
                status TEXT NOT NULL,
                filled_size REAL DEFAULT 0,
                avg_fill_price REAL,
                fee REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT,
                FOREIGN KEY (tradeset_id) REFERENCES tradesets(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fill_id TEXT UNIQUE NOT NULL,
                order_id TEXT NOT NULL,
                price REAL NOT NULL,
                size REAL NOT NULL,
                fee REAL DEFAULT 0,
                timestamp REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tradesets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                yes_order_id TEXT,
                no_order_id TEXT,
                yes_cost REAL,
                no_cost REAL,
                total_cost REAL,
                total_fees REAL DEFAULT 0,
                expected_payout REAL DEFAULT 1.0,
                realized_pnl REAL,
                resolution_outcome TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                market_id TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunities_market 
            ON opportunities(market_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunities_timestamp 
            ON opportunities(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_tradeset 
            ON orders(tradeset_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fills_order 
            ON fills(order_id)
        """)

        self._conn.commit()

    def log_opportunity(self, signal: TradeSignal) -> int:
        """Log a detected opportunity (whether traded or skipped)."""
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT INTO opportunities 
            (market_id, timestamp, yes_ask, no_ask, yes_size, no_size, 
             sum_cost, edge, cost_buffer, decision, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal.market_id,
            signal.timestamp,
            float(signal.yes_ask) if signal.yes_ask else None,
            float(signal.no_ask) if signal.no_ask else None,
            float(signal.yes_size) if signal.yes_size else None,
            float(signal.no_size) if signal.no_size else None,
            float(signal.sum_cost) if signal.sum_cost else None,
            float(signal.edge) if signal.edge else None,
            float(signal.cost_buffer),
            signal.decision.value,
            signal.reason,
        ))
        self._conn.commit()
        return cursor.lastrowid

    def create_tradeset(self, market_id: str) -> int:
        """Create a new tradeset for a complete-set trade attempt."""
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT INTO tradesets (market_id, status)
            VALUES (?, 'pending')
        """, (market_id,))
        self._conn.commit()
        return cursor.lastrowid

    def update_tradeset(
        self,
        tradeset_id: int,
        status: Optional[str] = None,
        yes_order_id: Optional[str] = None,
        no_order_id: Optional[str] = None,
        yes_cost: Optional[Decimal] = None,
        no_cost: Optional[Decimal] = None,
        total_fees: Optional[Decimal] = None,
        realized_pnl: Optional[Decimal] = None,
        resolution_outcome: Optional[str] = None,
    ) -> None:
        """Update a tradeset with new information."""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if yes_order_id is not None:
            updates.append("yes_order_id = ?")
            params.append(yes_order_id)
        if no_order_id is not None:
            updates.append("no_order_id = ?")
            params.append(no_order_id)
        if yes_cost is not None:
            updates.append("yes_cost = ?")
            params.append(float(yes_cost))
        if no_cost is not None:
            updates.append("no_cost = ?")
            params.append(float(no_cost))
        if yes_cost is not None and no_cost is not None:
            updates.append("total_cost = ?")
            params.append(float(yes_cost + no_cost))
        if total_fees is not None:
            updates.append("total_fees = ?")
            params.append(float(total_fees))
        if realized_pnl is not None:
            updates.append("realized_pnl = ?")
            params.append(float(realized_pnl))
        if resolution_outcome is not None:
            updates.append("resolution_outcome = ?")
            params.append(resolution_outcome)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(tradeset_id)

            cursor = self._conn.cursor()
            cursor.execute(f"""
                UPDATE tradesets SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            self._conn.commit()

    def log_order(
        self,
        order_id: str,
        tradeset_id: int,
        market_id: str,
        token_id: str,
        side: str,
        order_type: str,
        price: Decimal,
        size: Decimal,
        status: str,
    ) -> None:
        """Log a placed order."""
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT INTO orders 
            (order_id, tradeset_id, market_id, token_id, side, order_type, 
             price, size, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_id,
            tradeset_id,
            market_id,
            token_id,
            side,
            order_type,
            float(price),
            float(size),
            status,
        ))
        self._conn.commit()

    def update_order(
        self,
        order_id: str,
        status: Optional[str] = None,
        filled_size: Optional[Decimal] = None,
        avg_fill_price: Optional[Decimal] = None,
        fee: Optional[Decimal] = None,
    ) -> None:
        """Update an existing order."""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if filled_size is not None:
            updates.append("filled_size = ?")
            params.append(float(filled_size))
        if avg_fill_price is not None:
            updates.append("avg_fill_price = ?")
            params.append(float(avg_fill_price))
        if fee is not None:
            updates.append("fee = ?")
            params.append(float(fee))

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(order_id)

            cursor = self._conn.cursor()
            cursor.execute(f"""
                UPDATE orders SET {', '.join(updates)}
                WHERE order_id = ?
            """, params)
            self._conn.commit()

    def log_fill(
        self,
        fill_id: str,
        order_id: str,
        price: Decimal,
        size: Decimal,
        fee: Decimal,
        timestamp: float,
    ) -> None:
        """Log a fill for an order."""
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT INTO fills (fill_id, order_id, price, size, fee, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fill_id, order_id, float(price), float(size), float(fee), timestamp))
        self._conn.commit()

    def log_risk_event(
        self,
        event_type: str,
        market_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a risk event (partial fill, reject, disconnect, etc.)."""
        cursor = self._conn.cursor()
        cursor.execute("""
            INSERT INTO risk_events (event_type, market_id, details)
            VALUES (?, ?, ?)
        """, (event_type, market_id, json.dumps(details) if details else None))
        self._conn.commit()

    def get_opportunities_summary(self) -> Dict[str, Any]:
        """Get summary statistics for opportunities."""
        cursor = self._conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM opportunities")
        total = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM opportunities WHERE decision = ?",
            (SignalDecision.TRADE.value,)
        )
        traded = cursor.fetchone()[0]

        cursor.execute(
            "SELECT AVG(edge) FROM opportunities WHERE edge IS NOT NULL"
        )
        avg_edge = cursor.fetchone()[0]

        cursor.execute(
            "SELECT AVG(sum_cost) FROM opportunities WHERE sum_cost IS NOT NULL"
        )
        avg_sum_cost = cursor.fetchone()[0]

        cursor.execute("""
            SELECT decision, COUNT(*) as count 
            FROM opportunities 
            GROUP BY decision
        """)
        by_decision = {row['decision']: row['count'] for row in cursor.fetchall()}

        return {
            'total_opportunities': total,
            'traded': traded,
            'skipped': total - traded,
            'avg_edge': avg_edge,
            'avg_sum_cost': avg_sum_cost,
            'by_decision': by_decision,
        }

    def get_tradesets_summary(self) -> Dict[str, Any]:
        """Get summary statistics for tradesets."""
        cursor = self._conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tradesets")
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM tradesets 
            GROUP BY status
        """)
        by_status = {row['status']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT SUM(realized_pnl) FROM tradesets 
            WHERE realized_pnl IS NOT NULL
        """)
        total_pnl = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT SUM(total_fees) FROM tradesets 
            WHERE total_fees IS NOT NULL
        """)
        total_fees = cursor.fetchone()[0] or 0

        return {
            'total_tradesets': total,
            'by_status': by_status,
            'total_pnl': total_pnl,
            'total_fees': total_fees,
        }

    def get_risk_events_count(self, hours: int = 1) -> Dict[str, int]:
        """Get count of risk events in the last N hours."""
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT event_type, COUNT(*) as count
            FROM risk_events
            WHERE created_at > datetime('now', ?)
            GROUP BY event_type
        """, (f'-{hours} hours',))
        return {row['event_type']: row['count'] for row in cursor.fetchall()}
