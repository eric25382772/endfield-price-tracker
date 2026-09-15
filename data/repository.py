from data.models import get_db
from config import get_game_date


def get_all_items():
    """撈出資料庫裡全部的物品。"""
    conn = get_db()
    items = conn.execute("SELECT * FROM items ORDER BY id").fetchall()
    conn.close()
    return [dict(item) for item in items]


def get_items_by_region(region):
    """撈出某個地區的物品。"""
    conn = get_db()
    items = conn.execute("SELECT * FROM items WHERE region = ? ORDER BY id", (region,)).fetchall()
    conn.close()
    return [dict(item) for item in items]


def upsert_price(item_id, market_price, game_date=None, source='manual'):
    """寫入我的價格；同一天同一物品已存在就覆蓋。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        INSERT INTO prices (item_id, market_price, game_date, source, recorded_at)
        VALUES (?, ?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(item_id, game_date)
        DO UPDATE SET market_price = excluded.market_price,
                      source = excluded.source,
                      recorded_at = datetime('now','localtime')
    """, (item_id, market_price, game_date, source))
    conn.commit()
    conn.close()


def upsert_quota(region, remaining, max_quota, game_date=None):
    """寫入某地區的購買配額；同一天已存在就覆蓋。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        INSERT INTO quotas (region, remaining, max_quota, game_date, recorded_at)
        VALUES (?, ?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(region, game_date)
        DO UPDATE SET remaining = excluded.remaining,
                      max_quota = excluded.max_quota,
                      recorded_at = datetime('now','localtime')
    """, (region, remaining, max_quota, game_date))
    conn.commit()
    conn.close()


def get_quota(region, game_date=None):
    """讀取某地區、某天的購買配額。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    row = conn.execute("""
        SELECT * FROM quotas WHERE region = ? AND game_date = ?
    """, (region, game_date)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_friend_prices_for_item(item_id, game_date=None):
    """清掉某物品某天的所有好友價（重掃前先清，免得新舊混在一起）。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        DELETE FROM friend_prices WHERE item_id = ? AND game_date = ?
    """, (item_id, game_date))
    conn.commit()
    conn.close()


def upsert_friend_price(item_id, market_price, friend_name='好友', game_date=None, source='ocr'):
    """寫入一筆好友價；同一天同一物品同一好友已存在就覆蓋。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        INSERT INTO friend_prices (item_id, friend_name, market_price, game_date, source, recorded_at)
        VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(item_id, friend_name, game_date)
        DO UPDATE SET market_price = excluded.market_price,
                      source = excluded.source,
                      recorded_at = datetime('now','localtime')
    """, (item_id, friend_name, market_price, game_date, source))
    conn.commit()
    conn.close()


# ===== 好友名稱正規化（v4.1） =====

def get_friend_name_alias(raw_name):
    """查單一 raw OCR 字串的正解名稱；無則回 None。掃描器用它判斷是否可跳過日韓回退。"""
    conn = get_db()
    row = conn.execute(
        "SELECT canonical FROM friend_names WHERE raw_name = ?", (raw_name,)).fetchone()
    conn.close()
    return row['canonical'] if row else None


def set_friend_name_alias(raw_name, canonical, source='ocr_fallback'):
    """記住 raw → canonical 對應。source='user' 會覆寫 'ocr_fallback'（手動修正優先）。"""
    conn = get_db()
    conn.execute("""
        INSERT INTO friend_names (raw_name, canonical, source, updated_at)
        VALUES (?, ?, ?, datetime('now','localtime'))
        ON CONFLICT(raw_name) DO UPDATE SET canonical = excluded.canonical,
                                            source = excluded.source,
                                            updated_at = datetime('now','localtime')
    """, (raw_name, canonical, source))
    conn.commit()
    conn.close()


def get_friend_name_aliases():
    """回傳 {raw_name: canonical} 整表，供 /compare 顯示時把舊資料名稱映成正解。"""
    conn = get_db()
    rows = conn.execute("SELECT raw_name, canonical FROM friend_names").fetchall()
    conn.close()
    return {row['raw_name']: row['canonical'] for row in rows}


def rename_friend_prices(raw_name, canonical):
    """把 friend_prices 裡所有 raw 名字（不分日期）改寫成正解，讓底層資料也乾淨。
    OR IGNORE 避開 UNIQUE(item_id, friend_name, game_date) 撞列的極少數情況。
    回傳改動的列數。"""
    if raw_name == canonical:
        return 0
    conn = get_db()
    cur = conn.execute(
        "UPDATE OR IGNORE friend_prices SET friend_name = ? WHERE friend_name = ?",
        (canonical, raw_name))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


# 整區（get_profit_comparison）與單一物品（get_item_profit）只差 WHERE 與排序，SQL 本體共用一份。
# 兩者原本是各自一份複製品：表格走前者、網頁手動改價後的即時回填走後者，改到一邊漏一邊
# 就會出現「表格跟改完的那列對不上」。{where} 只填程式內固定字串，不接外部輸入。
_PROFIT_SQL = """
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
    WHERE {where}
"""


def get_profit_comparison(region, game_date=None):
    """把我的價格和好友最高價湊成一列、算出利潤，依利潤由高到低排。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    rows = conn.execute(_PROFIT_SQL.format(where='i.region = ?') + """
        ORDER BY
            CASE WHEN p.market_price IS NOT NULL AND fp_best.best_price IS NOT NULL
                 THEN fp_best.best_price - p.market_price END DESC
    """, (game_date, game_date, region)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_item_profit(item_id, game_date=None):
    """只取單一物品的利潤比對結果。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    row = conn.execute(_PROFIT_SQL.format(where='i.id = ?'),
                       (game_date, game_date, item_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_stockpile(item_id, buy_price, region, game_date=None):
    """記錄囤貨（持有區偵測到的物品）。同一天同物品只記一筆。"""
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    conn.execute("""
        INSERT INTO stockpile (item_id, buy_price, quantity, game_date_bought, region, recorded_at)
        VALUES (?, ?, 1, ?, ?, datetime('now','localtime'))
        ON CONFLICT(item_id, game_date_bought)
        DO UPDATE SET buy_price = excluded.buy_price,
                      recorded_at = datetime('now','localtime')
    """, (item_id, buy_price, game_date, region))
    conn.commit()
    conn.close()


def get_active_stockpile(game_date=None):
    """取得 game_date 當天的囤貨，搭配好友最高價與出價好友名計算利潤。

    v6.1：只查當天。囤貨是「今天買、今天賣」的當日操作，跨日合併會讓
    昨天的買價混進今天的清單。好友最高價同樣只取當天的：跨天沿用上次
    掃到的價格會讓沒掃的日子看起來仍有利潤，實際上是幾天前的舊值。
    """
    if game_date is None:
        game_date = get_game_date()
    conn = get_db()
    rows = conn.execute("""
        SELECT s.id, s.item_id,
               i.name_cn, i.name_en, i.region,
               s.buy_price,
               s.game_date_bought,
               fp.market_price AS friend_best_price,
               fp.friend_name  AS friend_best_name
        FROM stockpile s
        JOIN items i ON s.item_id = i.id
        LEFT JOIN friend_prices fp
               ON fp.id = (SELECT f2.id FROM friend_prices f2
                           WHERE f2.item_id = s.item_id AND f2.game_date = ?
                           ORDER BY f2.market_price DESC LIMIT 1)
        WHERE s.sold = 0 AND s.game_date_bought = ?
        ORDER BY i.region, s.id
    """, (game_date, game_date)).fetchall()
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
            INSERT INTO stockpile (item_id, buy_price, quantity, game_date_bought, region, sold, recorded_at)
            VALUES (?, ?, 1, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(item_id, game_date_bought)
            DO UPDATE SET buy_price = excluded.buy_price,
                          region = excluded.region,
                          sold = excluded.sold,
                          recorded_at = datetime('now','localtime')
        """, (s['item_id'], s['buy_price'], game_date, s.get('region'), s.get('sold', 0)))
    conn.commit()
    conn.close()


def get_available_dates(limit=30):
    """列出有價格資料的所有日期。"""
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT game_date FROM prices
        ORDER BY game_date DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [row['game_date'] for row in rows]


def get_price_history(item_id, days=30):
    """取得某物品最近 N 個遊戲日的我方市場價時間序列（依日期遞增）。"""
    conn = get_db()
    rows = conn.execute("""
        SELECT game_date, market_price
        FROM prices
        WHERE item_id = ?
          AND game_date >= date(?, ?)
        ORDER BY game_date ASC
    """, (item_id, get_game_date(), f'-{days - 1} days')).fetchall()
    conn.close()
    return [(r['game_date'], r['market_price']) for r in rows]


def get_price_extremes(item_id):
    """取得某物品全期極值：我方買價的最低/最高、好友賣價的最高（不限天數）。"""
    conn = get_db()
    my = conn.execute("""
        SELECT MIN(market_price) AS lo, MAX(market_price) AS hi
        FROM prices WHERE item_id = ?
    """, (item_id,)).fetchone()
    fr = conn.execute("""
        SELECT MAX(market_price) AS hi
        FROM friend_prices WHERE item_id = ?
    """, (item_id,)).fetchone()
    conn.close()
    return {'my_low': my['lo'], 'my_high': my['hi'], 'sell_ceiling': fr['hi']}


def get_friend_max_price_history(item_id, days=30):
    """取得某物品最近 N 個遊戲日的好友最高價時間序列（依日期遞增）。"""
    conn = get_db()
    rows = conn.execute("""
        SELECT game_date, MAX(market_price) AS max_price
        FROM friend_prices
        WHERE item_id = ?
          AND game_date >= date(?, ?)
        GROUP BY game_date
        ORDER BY game_date ASC
    """, (item_id, get_game_date(), f'-{days - 1} days')).fetchall()
    conn.close()
    return [(r['game_date'], r['max_price']) for r in rows]
