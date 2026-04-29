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


def delete_friend_prices_for_item(item_id, game_date=None):
    """Delete all friend prices for a specific item on a date (before re-scanning)."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        DELETE FROM friend_prices WHERE item_id = ? AND game_date = ?
    """, (item_id, game_date))
    conn.commit()
    conn.close()


def upsert_friend_price(item_id, market_price, friend_name='好友', game_date=None, source='ocr'):
    """Insert or update a friend's price record."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        INSERT INTO friend_prices (item_id, friend_name, market_price, game_date, source)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(item_id, friend_name, game_date)
        DO UPDATE SET market_price = excluded.market_price,
                      source = excluded.source,
                      recorded_at = CURRENT_TIMESTAMP
    """, (item_id, friend_name, market_price, game_date, source))
    conn.commit()
    conn.close()


def get_friend_prices_by_date_and_region(region, friend_name=None, game_date=None):
    """Get friend prices for a region. If friend_name is None, get best (highest) price per item."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    if friend_name:
        rows = conn.execute("""
            SELECT i.id as item_id, i.name_cn, i.name_en, i.base_price, i.region,
                   fp.market_price, fp.friend_name, fp.source, fp.recorded_at
            FROM items i
            LEFT JOIN friend_prices fp ON i.id = fp.item_id AND fp.game_date = ? AND fp.friend_name = ?
            WHERE i.region = ?
            ORDER BY i.id
        """, (game_date, friend_name, region)).fetchall()
    else:
        # Get the highest friend price per item (best selling opportunity)
        rows = conn.execute("""
            SELECT i.id as item_id, i.name_cn, i.name_en, i.base_price, i.region,
                   fp.market_price, fp.friend_name, fp.source, fp.recorded_at
            FROM items i
            LEFT JOIN (
                SELECT item_id, market_price, friend_name, source, recorded_at
                FROM friend_prices
                WHERE game_date = ?
                AND market_price = (
                    SELECT MAX(fp2.market_price)
                    FROM friend_prices fp2
                    WHERE fp2.item_id = friend_prices.item_id AND fp2.game_date = friend_prices.game_date
                )
            ) fp ON i.id = fp.item_id
            WHERE i.region = ?
            ORDER BY i.id
        """, (game_date, region)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_friend_names(game_date=None):
    """Get list of friend names that have price data for a date."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT friend_name FROM friend_prices
        WHERE game_date = ? ORDER BY friend_name
    """, (game_date,)).fetchall()
    conn.close()
    return [row['friend_name'] for row in rows]


def get_profit_comparison(region, game_date=None):
    """Compare self prices vs best friend prices, calculate profit, sorted by profit desc."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    rows = conn.execute("""
        SELECT i.id as item_id, i.name_cn, i.name_en, i.base_price, i.region,
               p.market_price as my_price,
               fp_best.best_price as friend_price,
               fp_best.best_friend_name as best_friend,
               CASE
                   WHEN p.market_price IS NOT NULL AND fp_best.best_price IS NOT NULL
                   THEN fp_best.best_price - p.market_price
                   ELSE NULL
               END as profit
        FROM items i
        LEFT JOIN prices p ON i.id = p.item_id AND p.game_date = ?
        LEFT JOIN (
            SELECT fp.item_id,
                   fp.market_price as best_price,
                   fp.friend_name as best_friend_name
            FROM friend_prices fp
            WHERE fp.game_date = ?
              AND fp.market_price = (
                  SELECT MAX(fp2.market_price)
                  FROM friend_prices fp2
                  WHERE fp2.item_id = fp.item_id AND fp2.game_date = fp.game_date
              )
            GROUP BY fp.item_id
        ) fp_best ON i.id = fp_best.item_id
        WHERE i.region = ?
        ORDER BY
            CASE WHEN p.market_price IS NOT NULL AND fp_best.best_price IS NOT NULL
                 THEN fp_best.best_price - p.market_price END DESC
    """, (game_date, game_date, region)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_item_profit(item_id, game_date=None):
    """Get profit comparison data for a single item."""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    row = conn.execute("""
        SELECT i.id as item_id, i.name_cn, i.name_en, i.base_price, i.region,
               p.market_price as my_price,
               fp_best.best_price as friend_price,
               fp_best.best_friend_name as best_friend,
               CASE
                   WHEN p.market_price IS NOT NULL AND fp_best.best_price IS NOT NULL
                   THEN fp_best.best_price - p.market_price
                   ELSE NULL
               END as profit
        FROM items i
        LEFT JOIN prices p ON i.id = p.item_id AND p.game_date = ?
        LEFT JOIN (
            SELECT fp.item_id,
                   fp.market_price as best_price,
                   fp.friend_name as best_friend_name
            FROM friend_prices fp
            WHERE fp.game_date = ?
              AND fp.market_price = (
                  SELECT MAX(fp2.market_price)
                  FROM friend_prices fp2
                  WHERE fp2.item_id = fp.item_id AND fp2.game_date = fp.game_date
              )
            GROUP BY fp.item_id
        ) fp_best ON i.id = fp_best.item_id
        WHERE i.id = ?
    """, (game_date, game_date, item_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_stockpile(item_id, buy_price, region, game_date=None):
    """記錄囤貨（持有區偵測到的物品）。同一天同物品只記一筆。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        INSERT INTO stockpile (item_id, buy_price, quantity, game_date_bought, region)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(item_id, game_date_bought)
        DO UPDATE SET buy_price = excluded.buy_price,
                      recorded_at = CURRENT_TIMESTAMP
    """, (item_id, buy_price, game_date, region))
    conn.commit()
    conn.close()


def get_active_stockpile():
    """取得所有未賣出的囤貨，搭配好友最高價計算利潤。

    同一 item_id 跨遊戲日重複插入時，UI 端壓成一列：
    取最早 game_date_bought、最低 buy_price，id 取代表列（最早那筆）。
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT g.item_id,
               (SELECT s2.id FROM stockpile s2
                WHERE s2.item_id = g.item_id AND s2.sold = 0
                ORDER BY s2.game_date_bought ASC, s2.id ASC LIMIT 1) AS id,
               i.name_cn, i.name_en, i.region,
               g.buy_price,
               g.game_date_bought,
               (SELECT MAX(fp.market_price)
                FROM friend_prices fp
                WHERE fp.item_id = g.item_id
                  AND fp.game_date = (SELECT MAX(fp2.game_date) FROM friend_prices fp2 WHERE fp2.item_id = g.item_id)
               ) as friend_best_price
        FROM (
            SELECT item_id,
                   MIN(game_date_bought) AS game_date_bought,
                   MIN(buy_price) AS buy_price
            FROM stockpile
            WHERE sold = 0
            GROUP BY item_id
        ) g
        JOIN items i ON g.item_id = i.id
        ORDER BY g.game_date_bought DESC
    """).fetchall()
    conn.close()
    results = []
    for row in rows:
        r = dict(row)
        if r['friend_best_price'] is not None:
            r['stockpile_profit'] = r['friend_best_price'] - r['buy_price']
        else:
            r['stockpile_profit'] = None
        results.append(r)
    return results


def mark_stockpile_sold(stockpile_id):
    """標記囤貨為已賣出。"""
    conn = get_db()
    conn.execute("UPDATE stockpile SET sold = 1 WHERE id = ?", (stockpile_id,))
    conn.commit()
    conn.close()


def mark_stockpile_sold_by_item(item_id):
    """標記某物品所有未賣出的囤貨為已賣出（合併顯示後一鍵清掉）。"""
    conn = get_db()
    conn.execute("UPDATE stockpile SET sold = 1 WHERE item_id = ? AND sold = 0", (item_id,))
    conn.commit()
    conn.close()


def snapshot_date(game_date):
    """匯出指定日期的所有資料（prices / friend_prices / quotas / stockpile）為 dict。"""
    conn = get_db()
    prices = [dict(r) for r in conn.execute(
        "SELECT item_id, market_price, source FROM prices WHERE game_date = ?",
        (game_date,)).fetchall()]
    friend_prices = [dict(r) for r in conn.execute(
        "SELECT item_id, friend_name, market_price, source FROM friend_prices WHERE game_date = ?",
        (game_date,)).fetchall()]
    quotas = [dict(r) for r in conn.execute(
        "SELECT region, remaining, max_quota FROM quotas WHERE game_date = ?",
        (game_date,)).fetchall()]
    stockpile = [dict(r) for r in conn.execute(
        "SELECT item_id, buy_price, region, sold FROM stockpile WHERE game_date_bought = ?",
        (game_date,)).fetchall()]
    conn.close()
    return {
        'game_date': game_date,
        'prices': prices,
        'friend_prices': friend_prices,
        'quotas': quotas,
        'stockpile': stockpile,
    }


def delete_date_data(game_date):
    """刪除指定日期的所有掃描/好友/配額/囤貨資料。"""
    conn = get_db()
    conn.execute("DELETE FROM prices WHERE game_date = ?", (game_date,))
    conn.execute("DELETE FROM friend_prices WHERE game_date = ?", (game_date,))
    conn.execute("DELETE FROM quotas WHERE game_date = ?", (game_date,))
    conn.execute("DELETE FROM stockpile WHERE game_date_bought = ?", (game_date,))
    conn.commit()
    conn.close()


def restore_snapshot(snapshot):
    """把 snapshot_date 輸出的 dict 寫回資料庫。"""
    game_date = snapshot['game_date']
    for p in snapshot.get('prices', []):
        upsert_price(p['item_id'], p['market_price'],
                     game_date=game_date, source=p.get('source', 'scanner'))
    for fp in snapshot.get('friend_prices', []):
        upsert_friend_price(fp['item_id'], fp['market_price'],
                            friend_name=fp.get('friend_name', '好友'),
                            game_date=game_date, source=fp.get('source', 'ocr'))
    for q in snapshot.get('quotas', []):
        upsert_quota(q['region'], q['remaining'], q['max_quota'], game_date=game_date)
    conn = get_db()
    for s in snapshot.get('stockpile', []):
        conn.execute("""
            INSERT INTO stockpile (item_id, buy_price, quantity, game_date_bought, region, sold)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(item_id, game_date_bought)
            DO UPDATE SET buy_price = excluded.buy_price,
                          region = excluded.region,
                          sold = excluded.sold,
                          recorded_at = CURRENT_TIMESTAMP
        """, (s['item_id'], s['buy_price'], game_date, s.get('region'), s.get('sold', 0)))
    conn.commit()
    conn.close()


def get_available_dates(limit=30):
    """Get list of dates that have price data."""
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT game_date FROM prices
        ORDER BY game_date DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [row['game_date'] for row in rows]
