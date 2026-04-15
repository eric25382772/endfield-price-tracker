from flask import Flask, render_template, request, redirect, url_for, flash
from config import REGIONS, get_game_date, PROFIT_THRESHOLD, STOCKPILE_THRESHOLD
from data.models import init_db
from data.items import REGION_QUOTA
from data.repository import (
    upsert_price, upsert_quota, get_quota,
    get_available_dates,
    upsert_friend_price,
    get_friend_names, get_profit_comparison,
    get_active_stockpile, mark_stockpile_sold
)

app = Flask(__name__)
app.secret_key = 'endfield-price-tracker-secret'


@app.route('/')
def index():
    return redirect(url_for('compare'))


@app.route('/manual', methods=['POST'])
def manual_input():
    item_id = request.form.get('item_id', type=int)
    market_price = request.form.get('market_price', type=int)
    game_date = request.form.get('game_date')

    if not all([item_id, market_price]):
        flash('請填寫所有欄位', 'danger')
        return redirect(url_for('index'))

    if market_price < 100 or market_price > 8000:
        flash('價格必須在 100-8000 之間', 'danger')
        return redirect(url_for('index'))

    upsert_price(item_id, market_price, game_date=game_date, source='manual')
    flash(f'已儲存價格：{market_price}', 'success')
    return redirect(url_for('index', date=game_date))


@app.route('/quota', methods=['POST'])
def update_quota():
    region = request.form.get('region')
    remaining = request.form.get('remaining', type=int)
    game_date = request.form.get('game_date')
    quota_info = REGION_QUOTA.get(region, {})
    max_quota = quota_info.get('max', 0)

    if region and remaining is not None:
        upsert_quota(region, remaining, max_quota, game_date=game_date)
        flash(f'已更新 {REGIONS.get(region, region)} 剩餘配額：{remaining}/{max_quota}', 'success')
    return redirect(url_for('index', date=game_date))


@app.route('/compare')
def compare():
    """利潤比對頁面 - 自己 vs 好友價格"""
    selected_date = request.args.get('date')
    current_date = get_game_date()
    date = selected_date or current_date
    available = get_available_dates()
    friends = get_friend_names(date)

    valley_comparison = get_profit_comparison('valley_iv', date)
    wuling_comparison = get_profit_comparison('wuling', date)

    # 擇一最高利潤（配額限制下實際只能挑一種貨買）
    def pick_best(rows):
        profitable = [r for r in rows if r['profit'] is not None and r['profit'] > 0]
        return max(profitable, key=lambda x: x['profit']) if profitable else None

    valley_best = pick_best(valley_comparison)
    wuling_best = pick_best(wuling_comparison)

    # 跨區 Top 5 排行
    all_items = valley_comparison + wuling_comparison
    profitable = [r for r in all_items if r['profit'] is not None and r['profit'] > 0]
    profitable.sort(key=lambda x: x['profit'], reverse=True)

    # 囤貨 + 剩餘配額
    stockpile = get_active_stockpile()
    valley_quota = get_quota('valley_iv', date)
    wuling_quota = get_quota('wuling', date)

    return render_template('compare.html',
                           valley_comparison=valley_comparison,
                           wuling_comparison=wuling_comparison,
                           valley_best=valley_best,
                           wuling_best=wuling_best,
                           top_profitable=profitable[:5],
                           friends=friends,
                           stockpile=stockpile,
                           valley_quota=valley_quota,
                           wuling_quota=wuling_quota,
                           region_quota=REGION_QUOTA,
                           profit_threshold=PROFIT_THRESHOLD,
                           stockpile_threshold=STOCKPILE_THRESHOLD,
                           current_date=current_date,
                           selected_date=selected_date,
                           available_dates=available)


@app.route('/friend/manual', methods=['POST'])
def friend_manual_input():
    """手動輸入好友價格"""
    item_id = request.form.get('item_id', type=int)
    market_price = request.form.get('market_price', type=int)
    friend_name = request.form.get('friend_name', '好友')
    game_date = request.form.get('game_date')

    if not all([item_id, market_price]):
        flash('請填寫所有欄位', 'danger')
        return redirect(url_for('compare'))

    if market_price < 100 or market_price > 8000:
        flash('價格必須在 100-8000 之間', 'danger')
        return redirect(url_for('compare'))

    upsert_friend_price(item_id, market_price, friend_name=friend_name,
                        game_date=game_date, source='manual')
    flash(f'已儲存好友價格：{market_price}', 'success')
    return redirect(url_for('compare', date=game_date))


@app.route('/stockpile/sell', methods=['POST'])
def stockpile_sell():
    """標記囤貨為已賣出"""
    stockpile_id = request.form.get('stockpile_id', type=int)
    if stockpile_id:
        mark_stockpile_sold(stockpile_id)
        flash('已標記為賣出', 'success')
    return redirect(url_for('compare'))


if __name__ == '__main__':
    init_db()
    print("Server running at http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)
