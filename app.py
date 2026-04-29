import json
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from config import REGIONS, get_game_date, PROFIT_THRESHOLD, STOCKPILE_THRESHOLD
from data.models import init_db
from data.items import REGION_QUOTA, get_region_quota, get_visible_item_names
from data.repository import (
    upsert_price, upsert_quota, get_quota,
    get_available_dates,
    upsert_friend_price,
    get_friend_names, get_profit_comparison, get_item_profit,
    get_active_stockpile, mark_stockpile_sold_by_item,
    snapshot_date, delete_date_data, restore_snapshot,
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
    quota_info = get_region_quota(region, game_date) or {}
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

    # 依遊戲日期過濾：2026-04-17 之前武陵沒有息壤淨水濾心/清波筏
    valley_visible = get_visible_item_names('valley_iv', date)
    wuling_visible = get_visible_item_names('wuling', date)
    valley_comparison = [r for r in valley_comparison if r['name_cn'] in valley_visible]
    wuling_comparison = [r for r in wuling_comparison if r['name_cn'] in wuling_visible]

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

    backup_path = Path(__file__).parent / 'data' / f'reset_backup_{date}.json'
    has_backup = backup_path.exists()

    region_quota_for_date = {
        'valley_iv': get_region_quota('valley_iv', date),
        'wuling':    get_region_quota('wuling',    date),
    }

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
                           region_quota=region_quota_for_date,
                           profit_threshold=PROFIT_THRESHOLD,
                           stockpile_threshold=STOCKPILE_THRESHOLD,
                           current_date=current_date,
                           selected_date=selected_date,
                           available_dates=available,
                           has_backup=has_backup)


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
    """標記囤貨為已賣出（依 item_id 一次清掉所有 sold=0 紀錄）"""
    item_id = request.form.get('item_id', type=int)
    if item_id:
        mark_stockpile_sold_by_item(item_id)
        flash('已標記為賣出', 'success')
    return redirect(url_for('compare'))


@app.route('/api/price', methods=['POST'])
def api_price():
    """API：編輯我的價格"""
    data = request.get_json()
    item_id = data.get('item_id')
    market_price = data.get('market_price')
    game_date = data.get('game_date')

    if not all([item_id, market_price]):
        return jsonify(ok=False, error='請填寫所有欄位'), 400
    if not (100 <= market_price <= 8000):
        return jsonify(ok=False, error='價格必須在 100-8000 之間'), 400

    upsert_price(item_id, market_price, game_date=game_date, source='manual')
    row = get_item_profit(item_id, game_date)
    return jsonify(ok=True, **row)


@app.route('/api/friend-price', methods=['POST'])
def api_friend_price():
    """API：編輯好友價格"""
    data = request.get_json()
    item_id = data.get('item_id')
    market_price = data.get('market_price')
    friend_name = data.get('friend_name') or '好友'
    game_date = data.get('game_date')

    if not all([item_id, market_price]):
        return jsonify(ok=False, error='請填寫所有欄位'), 400
    if not (100 <= market_price <= 8000):
        return jsonify(ok=False, error='價格必須在 100-8000 之間'), 400

    upsert_friend_price(item_id, market_price, friend_name=friend_name,
                        game_date=game_date, source='manual')
    row = get_item_profit(item_id, game_date)
    return jsonify(ok=True, **row)


SCAN_STATUS_FILE = Path(__file__).parent / 'data' / 'scan_status.json'


def _backup_path(game_date):
    return Path(__file__).parent / 'data' / f'reset_backup_{game_date}.json'


@app.route('/reset', methods=['POST'])
def reset_today():
    """備份今天資料到 JSON 後，從 DB 清除，讓畫面回到空白狀態。"""
    game_date = request.form.get('game_date') or get_game_date()
    snapshot = snapshot_date(game_date)
    any_data = any(snapshot[k] for k in ('prices', 'friend_prices', 'quotas', 'stockpile'))
    if not any_data:
        flash(f'{game_date} 沒有資料可以重置', 'info')
        return redirect(url_for('compare', date=game_date))
    path = _backup_path(game_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding='utf-8')
    delete_date_data(game_date)
    flash(f'已重置 {game_date} 的畫面資料，可按「回復」還原', 'success')
    return redirect(url_for('compare', date=game_date))


@app.route('/restore', methods=['POST'])
def restore_today():
    """從 JSON 備份還原資料。"""
    game_date = request.form.get('game_date') or get_game_date()
    path = _backup_path(game_date)
    if not path.exists():
        flash(f'找不到 {game_date} 的備份', 'warning')
        return redirect(url_for('compare', date=game_date))
    try:
        snapshot = json.loads(path.read_text(encoding='utf-8'))
        restore_snapshot(snapshot)
        path.unlink()
        flash(f'已回復 {game_date} 的資料', 'success')
    except Exception as e:
        flash(f'回復失敗：{e}', 'danger')
    return redirect(url_for('compare', date=game_date))


HEARTBEAT_FILE = Path(__file__).parent / 'data' / 'heartbeat.json'


@app.route('/api/heartbeat', methods=['POST'])
def api_heartbeat():
    """網頁每 2 秒 ping 一次，scanner 沒收到心跳就自動退出。"""
    try:
        HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_FILE.write_text(
            json.dumps({'ts': datetime.now().isoformat()}),
            encoding='utf-8',
        )
    except Exception:
        pass
    return jsonify(ok=True)


@app.route('/api/status')
def api_status():
    """回傳 scanner 目前的辨識狀態（前端每 1.5 秒輪詢）。"""
    if not SCAN_STATUS_FILE.exists():
        return jsonify(phase='idle', region=None)
    try:
        return jsonify(**json.loads(SCAN_STATUS_FILE.read_text(encoding='utf-8')))
    except Exception:
        return jsonify(phase='idle', region=None)


F2_DECISION_FILE = Path(__file__).parent / 'data' / 'f2_decision.json'


def _write_f2_decision(action):
    try:
        F2_DECISION_FILE.parent.mkdir(parents=True, exist_ok=True)
        F2_DECISION_FILE.write_text(
            json.dumps({'action': action, 'ts': datetime.now().isoformat()}),
            encoding='utf-8',
        )
        return True
    except Exception:
        return False


@app.route('/api/f2_confirm', methods=['POST'])
def api_f2_confirm():
    """使用者按 modal「清空換區」按鈕。scanner 會清掉 f3_queue 並執行新 F2。"""
    ok = _write_f2_decision('confirm')
    return jsonify(ok=ok)


@app.route('/api/f2_cancel', methods=['POST'])
def api_f2_cancel():
    """使用者按 modal「取消」按鈕。scanner 會放棄這次 F2，保留 f3_queue。"""
    ok = _write_f2_decision('cancel')
    return jsonify(ok=ok)


if __name__ == '__main__':
    init_db()
    print("Server running at http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)
