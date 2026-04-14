import sqlite3
import os
from config import DB_PATH
from data.items import ELASTIC_GOODS


def get_db():
    """Get a database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize database schema and seed items."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_cn TEXT NOT NULL UNIQUE,
            name_en TEXT,
            base_price INTEGER DEFAULT 2000,
            region TEXT NOT NULL DEFAULT 'valley_iv'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            market_price INTEGER NOT NULL,
            game_date TEXT NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'ocr',
            UNIQUE(item_id, game_date)
        )
    """)

    # 好友價格紀錄
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS friend_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            friend_name TEXT NOT NULL DEFAULT '好友',
            market_price INTEGER NOT NULL,
            game_date TEXT NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'ocr',
            UNIQUE(item_id, friend_name, game_date)
        )
    """)

    # 囤貨紀錄
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stockpile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            buy_price INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            game_date_bought TEXT NOT NULL,
            region TEXT NOT NULL,
            sold INTEGER NOT NULL DEFAULT 0,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(item_id, game_date_bought)
        )
    """)

    # 購買配額紀錄
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quotas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region TEXT NOT NULL,
            remaining INTEGER NOT NULL,
            max_quota INTEGER NOT NULL,
            game_date TEXT NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(region, game_date)
        )
    """)

    # Seed items
    for item in ELASTIC_GOODS:
        cursor.execute(
            "INSERT OR IGNORE INTO items (name_cn, name_en, base_price, region) VALUES (?, ?, ?, ?)",
            (item["name_cn"], item["name_en"], item["base_price"], item["region"])
        )

    conn.commit()
    conn.close()


def reset_db():
    """Drop and recreate all tables."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()


if __name__ == "__main__":
    reset_db()
    print("Database reset and initialized successfully.")
