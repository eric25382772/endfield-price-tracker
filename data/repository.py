from data.models import get_db
from config import get_game_date


def get_all_items():
    """Get all items from the database."""
    conn = get_db()
    items = conn.execute("SELECT * FROM items ORDER BY id").fetchall()
    conn.close()
    return [dict(item) for item in items]


def get_items_by_region(region):
    """Get items for a specific region."""
    conn = get_db()
    items = conn.execute("SELECT * FROM items WHERE region = ? ORDER BY id", (region,)).fetchall()
    conn.close()
    return [dict(item) for item in items]


def upsert_price(item_id, market_price, game_date=None, source='manual'):
    """Insert or update a price record."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        INSERT INTO prices (item_id, market_price, game_date, source)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(item_id, game_date)
        DO UPDATE SET market_price = excluded.market_price,
                      source = excluded.source,
                      recorded_at = CURRENT_TIMESTAMP
    """, (item_id, market_price, game_date, source))
    conn.commit()
    conn.close()


def upsert_quota(region, remaining, max_quota, game_date=None):
    """Insert or update purchase quota for a region."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        INSERT INTO quotas (region, remaining, max_quota, game_date)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(region, game_date)
        DO UPDATE SET remaining = excluded.remaining,
                      max_quota = excluded.max_quota,
                      recorded_at = CURRENT_TIMESTAMP
    """, (region, remaining, max_quota, game_date))
    conn.commit()
    conn.close()


def get_quota(region, game_date=None):
    """Get purchase quota for a region on a date."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    row = conn.execute("""
        SELECT * FROM quotas WHERE region = ? AND game_date = ?
    """, (region, game_date)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_prices_by_date_and_region(region, game_date=None):
    """Get prices for a specific region and game date."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    rows = conn.execute("""
        SELECT i.id as item_id, i.name_cn, i.name_en, i.base_price, i.region,
               p.market_price, p.source, p.recorded_at
        FROM items i
        LEFT JOIN prices p ON i.id = p.item_id AND p.game_date = ?
        WHERE i.region = ?
        ORDER BY i.id
    """, (game_date, region)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_available_dates(limit=30):
    """Get list of dates that have price data."""
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT game_date FROM prices
        ORDER BY game_date DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [row['game_date'] for row in rows]
