import os
from flask import Flask, render_template, request, redirect, url_for, flash
from config import UPLOAD_FOLDER, REGIONS, get_game_date, allowed_file, PROFIT_THRESHOLD, STOCKPILE_THRESHOLD
from data.models import init_db
from data.items import REGION_QUOTA
from data.repository import (
    get_all_items, upsert_price, upsert_quota, get_quota,
    get_prices_by_date_and_region, get_available_dates,
    upsert_friend_price, get_friend_prices_by_date_and_region,
    get_friend_names, get_profit_comparison,
    get_active_stockpile, mark_stockpile_sold
)

app = Flask(__name__)
app.secret_key = 'endfield-price-tracker-secret'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB


@app.route('/')
def index():
    selected_date = request.args.get('date')
    current_date = get_game_date()
    date = selected_date or current_date
    valley_iv_prices = get_prices_by_date_and_region('valley_iv', date)
    wuling_prices = get_prices_by_date_and_region('wuling', date)
    available = get_available_dates()
    valley_quota = get_quota('valley_iv', date)
    wuling_quota = get_quota('wuling', date)
    return render_template('index.html',
                           valley_iv_prices=valley_iv_prices,
                           wuling_prices=wuling_prices,
                           current_date=current_date,
                           selected_date=selected_date,
                           available_dates=available,
                           valley_quota=valley_quota,
                           wuling_quota=wuling_quota,
                           region_quota=REGION_QUOTA)


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


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'GET':
        return render_template('upload.html')

    if 'screenshot' not in request.files:
        flash('請選擇截圖檔案', 'danger')
        return redirect(url_for('upload'))

    file = request.files['screenshot']
    if file.filename == '':
        flash('請選擇截圖檔案', 'danger')
        return redirect(url_for('upload'))

    if not allowed_file(file.filename):
        flash('不支援的檔案格式，請上傳 PNG/JPG/BMP', 'danger')
        return redirect(url_for('upload'))

    region = request.form.get('region', 'valley_iv')

    # Save uploaded file
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f'screenshot_{get_game_date()}_{region}.{ext}'
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        from ocr.preprocessor import preprocess_screenshot
        processed_path = preprocess_screenshot(filepath)

        from ocr.engine import recognize
        ocr_results = recognize(processed_path)

        from ocr.parser import parse_ocr_results
        items_db = get_all_items()
        parsed = parse_ocr_results(ocr_results, items_db)

        if not parsed:
            flash('OCR 未能辨識出任何物品或價格，請嘗試重新截圖或使用手動輸入', 'warning')
            return redirect(url_for('upload'))

        return render_template('upload_result.html',
                               results=parsed,
                               items=items_db,
                               region=region,
                               region_name=REGIONS.get(region, region),
                               game_date=get_game_date())

    except Exception as e:
        flash(f'OCR 處理失敗：{str(e)}', 'danger')
        return redirect(url_for('upload'))


@app.route('/confirm', methods=['POST'])
def confirm():
    region = request.form.get('region')
    game_date = request.form.get('game_date')
    count = request.form.get('count', type=int, default=0)
    saved = 0

    for i in range(count):
        enabled = request.form.get(f'enabled_{i}')
        if not enabled:
            continue

        item_id = request.form.get(f'item_id_{i}', type=int)
        price = request.form.get(f'price_{i}', type=int)

        if item_id and price and 100 <= price <= 8000:
            upsert_price(item_id, price, game_date=game_date, source='ocr')
            saved += 1

    flash(f'已儲存 {saved} 筆價格資料（{REGIONS.get(region, region)}）', 'success')
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

    # Calculate totals
    valley_total_profit = sum(r['profit'] for r in valley_comparison if r['profit'] is not None and r['profit'] > 0)
    wuling_total_profit = sum(r['profit'] for r in wuling_comparison if r['profit'] is not None and r['profit'] > 0)

    # Find the best item overall
    all_items = valley_comparison + wuling_comparison
    profitable = [r for r in all_items if r['profit'] is not None and r['profit'] > 0]
    profitable.sort(key=lambda x: x['profit'], reverse=True)

    # 囤貨資料
    stockpile = get_active_stockpile()

    return render_template('compare.html',
                           valley_comparison=valley_comparison,
                           wuling_comparison=wuling_comparison,
                           valley_total_profit=valley_total_profit,
                           wuling_total_profit=wuling_total_profit,
                           top_profitable=profitable[:5],
                           friends=friends,
                           stockpile=stockpile,
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
