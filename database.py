"""
Project Alpha Database Module
SQLite storage for whale lists and trade history
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import config


def get_connection():
    """Get SQLite database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database with required tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whale_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT UNIQUE NOT NULL,
            nickname TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active BOOLEAN DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS whale_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            whale_address TEXT NOT NULL,
            market_id TEXT,
            market_title TEXT,
            outcome TEXT,
            side TEXT,
            amount_usdc REAL,
            price REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poly_market_id TEXT,
            kalshi_market_id TEXT,
            market_title TEXT,
            poly_yes_price REAL,
            kalshi_no_price REAL,
            spread REAL,
            roi_percent REAL,
            poly_liquidity REAL,
            kalshi_liquidity REAL,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_type TEXT,
            venue TEXT,
            market_id TEXT,
            market_title TEXT,
            side TEXT,
            amount REAL,
            price REAL,
            pnl REAL,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


def add_whale_address(address: str, nickname: str = None) -> bool:
    """Add a new whale address to monitor."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO whale_addresses (address, nickname) VALUES (?, ?)',
            (address.lower(), nickname)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_whale_addresses() -> List[Dict]:
    """Get all active whale addresses."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM whale_addresses WHERE active = 1')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def remove_whale_address(address: str) -> bool:
    """Deactivate a whale address."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE whale_addresses SET active = 0 WHERE address = ?',
        (address.lower(),)
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def log_whale_trade(
    whale_address: str,
    market_id: str,
    market_title: str,
    outcome: str,
    side: str,
    amount_usdc: float,
    price: float
):
    """Log a detected whale trade."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO whale_trades 
        (whale_address, market_id, market_title, outcome, side, amount_usdc, price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (whale_address.lower(), market_id, market_title, outcome, side, amount_usdc, price))
    conn.commit()
    conn.close()


def get_recent_whale_trades(limit: int = 50) -> List[Dict]:
    """Get recent whale trades."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM whale_trades 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_arbitrage_opportunity(
    poly_market_id: str,
    kalshi_market_id: str,
    market_title: str,
    poly_yes_price: float,
    kalshi_no_price: float,
    spread: float,
    roi_percent: float,
    poly_liquidity: float,
    kalshi_liquidity: float
):
    """Save a detected arbitrage opportunity."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO arbitrage_opportunities 
        (poly_market_id, kalshi_market_id, market_title, poly_yes_price, 
         kalshi_no_price, spread, roi_percent, poly_liquidity, kalshi_liquidity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (poly_market_id, kalshi_market_id, market_title, poly_yes_price,
          kalshi_no_price, spread, roi_percent, poly_liquidity, kalshi_liquidity))
    conn.commit()
    conn.close()


def get_active_opportunities() -> List[Dict]:
    """Get active arbitrage opportunities."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM arbitrage_opportunities 
        WHERE status = 'active' 
        ORDER BY roi_percent DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def log_trade(
    trade_type: str,
    venue: str,
    market_id: str,
    market_title: str,
    side: str,
    amount: float,
    price: float,
    pnl: float = None,
    notes: str = None
):
    """Log a trade execution."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trade_history 
        (trade_type, venue, market_id, market_title, side, amount, price, pnl, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (trade_type, venue, market_id, market_title, side, amount, price, pnl, notes))
    conn.commit()
    conn.close()


def get_trade_history(limit: int = 100) -> List[Dict]:
    """Get trade history."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM trade_history 
        ORDER BY executed_at DESC 
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


init_database()
