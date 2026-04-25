"""
背景掃描程式 - 快捷鍵截圖 + OCR 自動辨識價格
F2: 掃描自己的市場價格（自動截取遊戲視窗）
F3: 掃描好友的市場價格
Ctrl+Shift+Q: 結束程式

辨識方式：圖片比對確認物品 + OCR 讀取價格
"""
import os
import re
import sys
import time
import json
import ctypes
import ctypes.wintypes
import tempfile
import subprocess
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from queue import Queue
import keyboard
import mss
import mss.tools

from config import get_game_date, REGIONS, UPLOAD_FOLDER
from data.models import init_db
from data.items import VALLEY_IV_GOODS, WULING_GOODS
from data.repository import (
    get_all_items, upsert_price, upsert_friend_price,
    delete_friend_prices_for_item, upsert_stockpile, upsert_quota
)
from data.items import REGION_QUOTA, get_region_quota
from ocr.engine import recognize
from ocr.parser import parse_ocr_results
from ocr.image_matcher import identify_items_by_image, get_card_positions, identify_friend_item


# State
flask_process = None
f2_queue = Queue()
f3_queue = Queue()
last_f2_region = None  # F2 掃完後記錄區域，F3 只在該區域內比對
my_scan_active = threading.Event()  # F2 辨識中，F3 需等待避免畫面混淆
f2_ready = threading.Event()  # F2 已成功完成過至少一次且目前未在跑，F3 才能處理

SCAN_STATUS_FILE = Path(__file__).parent / 'data' / 'scan_status.json'
HEARTBEAT_FILE = Path(__file__).parent / 'data' / 'heartbeat.json'
_shutdown_event = threading.Event()
_completed_count = 0  # 每完成一張截圖處理 +1，網頁偵測此計數變化即 reload


_last_error = ''  # F2 失敗訊息；成功或其他階段清空

F2_DECISION_FILE = Path(__file__).parent / 'data' / 'f2_decision.json'
f2_pending_lock = threading.Event()  # set 表示已有 F2 在等網頁 modal 確認
_drop_in_flight_f3 = threading.Event()  # 換區確認後通知 worker_f3 丟棄當前已 get 的截圖


def set_scan_status(phase, region=None, error=None):
    """寫入掃描狀態供網頁端輪詢（scanner 與 Flask 是不同行程，透過檔案交換）。
    error=None 表示不改變既有錯誤；空字串則清空。"""
    global _last_error
    if error is not None:
        _last_error = error
    try:
        SCAN_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCAN_STATUS_FILE.write_text(json.dumps({
            'phase': phase,
            'region': region,
            'completed': _completed_count,
            'error': _last_error,
            'updated_at': datetime.now().isoformat(timespec='seconds'),
        }), encoding='utf-8')
    except Exception:
        pass


def update_scan_error(error):
    """只更新 error 欄位，保留現有 phase / region（給 toast 警告用）。"""
    global _last_error
    _last_error = error
    try:
        if SCAN_STATUS_FILE.exists():
            data = json.loads(SCAN_STATUS_FILE.read_text(encoding='utf-8'))
        else:
            data = {'phase': 'idle', 'region': None, 'completed': _completed_count}
        data['error'] = error
        data['updated_at'] = datetime.now().isoformat(timespec='seconds')
        SCAN_STATUS_FILE.write_text(json.dumps(data), encoding='utf-8')
    except Exception:
        pass


def _patch_status_field(key, value):
    """更新 scan_status.json 的單一欄位，保留其他欄位。value=None 則移除該欄位。"""
    try:
        if SCAN_STATUS_FILE.exists():
            data = json.loads(SCAN_STATUS_FILE.read_text(encoding='utf-8'))
        else:
            data = {'phase': 'idle', 'region': None, 'completed': _completed_count, 'error': _last_error}
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
        data['updated_at'] = datetime.now().isoformat(timespec='seconds')
        SCAN_STATUS_FILE.write_text(json.dumps(data), encoding='utf-8')
    except Exception:
        pass


def set_pending_f2(count):
    """寫 pending_f2 欄位 → 網頁 modal 會自動彈出。"""
    _patch_status_field('pending_f2', {'count': count})


def clear_pending_f2():
    """移除 pending_f2 欄位 → 網頁 modal 自動關閉。"""
    _patch_status_field('pending_f2', None)


def ensure_flask():
    """確保 Flask 在運行，如果沒有就啟動它。"""
    global flask_process
    # 檢查是否還活著
    if flask_process and flask_process.poll() is None:
        return
    # 啟動 Flask
    app_path = os.path.join(os.path.dirname(__file__), 'app.py')
    flask_process = subprocess.Popen(
        [sys.executable, app_path],
        cwd=os.path.dirname(__file__),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print("  Flask 已自動啟動 (127.0.0.1:5000)")


def get_foreground_window_rect():
    """Get the foreground window's position and size using Win32 API."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()

    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))

    # Get window title for logging
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    return {
        'left': rect.left,
        'top': rect.top,
        'width': rect.right - rect.left,
        'height': rect.bottom - rect.top,
        'title': title
    }


def capture_foreground_window():
    """Capture the foreground window screenshot, return temp file path."""
    win = get_foreground_window_rect()
    print(f"  截取視窗: {win['title']} ({win['width']}x{win['height']})")

    with mss.mss() as sct:
        monitor = {
            'left': win['left'],
            'top': win['top'],
            'width': win['width'],
            'height': win['height'],
        }
        screenshot = sct.grab(monitor)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False, dir=UPLOAD_FOLDER)
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=tmp.name)
        return tmp.name


def detect_region(parsed_results):
    """Auto-detect region based on matched item names."""
    valley_names = {item['name_cn'] for item in VALLEY_IV_GOODS}
    wuling_names = {item['name_cn'] for item in WULING_GOODS}

    valley_count = 0
    wuling_count = 0

    for item in parsed_results:
        if item['item_name'] in valley_names:
            valley_count += 1
        elif item['item_name'] in wuling_names:
            wuling_count += 1

    if wuling_count > valley_count:
        return 'wuling'
    elif valley_count > 0:
        return 'valley_iv'
    return None


def extract_prices_from_ocr(ocr_results):
    """從 OCR 結果中提取所有價格數字及其位置。"""
    prices = []
    for block in ocr_results:
        text = block['text'].strip()
        match = re.search(r'^(\d{3,4})$', text)
        if not match:
            match = re.search(r'(\d{3,4})', text)
            if match and len(text) > len(match.group(0)) + 2:
                continue
        if match:
            val = int(match.group(1))
            if 400 <= val <= 6000:
                prices.append({
                    'price': val,
                    'center_x': block['center_x'],
                    'center_y': block['center_y'],
                    'text': text,
                })
    return prices


def match_prices_to_cards(card_results, price_blocks, img_height):
    """
    將 OCR 價格匹配到卡片位置。
    價格通常在物品圖片下方，所以 y 會更大，用 x 距離為主要匹配依據。
    """
    used = set()
    for card in card_results:
        cx = card['card_center_x']
        cy = card['card_center_y']
        best_price = None
        best_dist = float('inf')
        best_idx = -1

        for i, pb in enumerate(price_blocks):
            if i in used:
                continue
            # 價格應在卡片圖片下方或附近，x 要接近
            dx = abs(pb['center_x'] - cx)
            dy = pb['center_y'] - cy  # 價格通常在圖片下方
            # x 距離不能太遠 (卡片寬度一半以內)
            if dx > 200:
                continue
            # y 方向: 價格在圖片下方 0~400px 範圍
            if dy < -100 or dy > 400:
                continue
            dist = dx + abs(dy) * 0.3  # x 權重較高
            if dist < best_dist:
                best_dist = dist
                best_price = pb
                best_idx = i

        if best_price is not None:
            card['price'] = best_price['price']
            used.add(best_idx)
        else:
            card['price'] = None

    return card_results


def _normalize_digits(text):
    """把 OCR 常見的字母誤判修回數字（僅用於純數字欄位）：O→0、l/I→1、S→5、B→8。"""
    return (text.replace('O', '0').replace('o', '0').replace('D', '0').replace('Q', '0')
                .replace('l', '1').replace('I', '1')
                .replace('S', '5').replace('s', '5')
                .replace('B', '8'))


def parse_remaining_quota(ocr_results, region, market_y, game_date=None):
    """
    從 OCR 結果找出剩餘配額數字。
    遊戲市場畫面頂端會顯示類似「65/130」或「0/250」的配額數字。
    只看市場標題上方區域（market_y 之上），避免被價格數字干擾。
    max_quota 依遊戲日期決定（武陵 4/17 改版前為 130，之後為 250）。
    """
    quota_cfg = get_region_quota(region, game_date) if region else None
    if not quota_cfg:
        return None
    max_quota = quota_cfg['max']
    daily = quota_cfg['daily']

    search_area = [b for b in ocr_results if market_y <= 0 or b['center_y'] < market_y]
    pattern_slash = re.compile(r'(\d{1,4})\s*[/／]\s*(\d{2,4})')

    def _match(text):
        for m in pattern_slash.finditer(text):
            remaining, total = int(m.group(1)), int(m.group(2))
            if total == max_quota and 0 <= remaining <= max_quota:
                return remaining, total
        return None

    # 1) 單 block 直接命中（含字母誤判修正）
    best = None
    for block in search_area:
        for text in (block['text'], _normalize_digits(block['text'])):
            hit = _match(text)
            if hit:
                if best is None or block['center_y'] < best['y']:
                    best = {'remaining': hit[0], 'max': hit[1], 'y': block['center_y']}
                break
    if best:
        print(f"  剩餘配額: {best['remaining']}/{best['max']}")
        return {'remaining': best['remaining'], 'max': best['max']}

    # 2) 跨 block 重組：找含關鍵字的 block，取同 y 列所有 block 連成一整行再比對
    keywords = ('剩餘', '可購買', '數量', '購買')
    for anchor in search_area:
        if not any(k in anchor['text'] for k in keywords):
            continue
        ay = anchor['center_y']
        row_blocks = [b for b in search_area if abs(b['center_y'] - ay) < 50]
        row_blocks.sort(key=lambda b: b['center_x'])
        joined_raw = ''.join(b['text'] for b in row_blocks)
        for text in (joined_raw, _normalize_digits(joined_raw)):
            hit = _match(text)
            if hit:
                print(f"  剩餘配額 (跨 block): {hit[0]}/{hit[1]}")
                return {'remaining': hit[0], 'max': hit[1]}

    # 全部失敗：dump 搜尋區塊讓使用者回報
    print(f"  剩餘配額：未辨識到 X/{max_quota} 格式，略過")
    print(f"  [DEBUG] search_area 區塊（前 15 個）：")
    for b in search_area[:15]:
        print(f"    y={b['center_y']:.0f} x={b['center_x']:.0f}: {b['text']!r}")
    return None


def parse_holding_area(ocr_results, market_y, items_db):
    """
    解析「市場」文字上方的持有區物品。
    持有區顯示玩家目前持有的彈性物資名稱和買入價格。
    Returns: list of {'item_id', 'item_name', 'price'}
    """
    if market_y <= 0:
        return []

    holding_ocr = [b for b in ocr_results if b['center_y'] < market_y]
    if not holding_ocr:
        return []

    parsed = parse_ocr_results(holding_ocr, items_db)
    holdings = [r for r in parsed if r['item_id'] and r['price']]
    return holdings


def scan_with_image_match(filepath):
    """用圖片比對辨識物品 + OCR 讀取價格。回傳 (市場結果, 區域, 持有區結果)。"""
    # Step 1: OCR 取得所有文字 (用於偵測區域和提取價格)
    print("  OCR 辨識中...")
    ocr_results = recognize(filepath)
    print(f"  OCR 找到 {len(ocr_results)} 個文字區塊")

    # Step 2: 偵測區域 (用 OCR 文字判斷)
    items_db = get_all_items()
    parsed_for_detect = parse_ocr_results(ocr_results, items_db)
    region = detect_region(parsed_for_detect)

    if not region:
        print("  無法判斷區域，嘗試用舊方法")
        return parsed_for_detect, None, [], None

    region_name = REGIONS.get(region, region)
    print(f"  偵測到區域: {region_name}")

    # OCR 文字已經有物品名稱+價格配對，優先使用
    # 只過濾掉「市場」標題上方（持有區）的結果
    market_y = 0
    for block in ocr_results:
        if '市場' in block['text']:
            market_y = block['center_y']
            break

    # 解析持有區（市場文字上方）
    holdings = parse_holding_area(ocr_results, market_y, items_db)
    if holdings:
        print(f"  持有區偵測到 {len(holdings)} 項囤貨:")
        for h in holdings:
            print(f"    [囤貨] {h['item_name']} = {h['price']}")

    # 解析剩餘配額（市場文字上方）
    quota = parse_remaining_quota(ocr_results, region, market_y, game_date=get_game_date())

    if market_y > 0:
        # 重新解析，只用市場區域內的 OCR 結果
        market_ocr = [b for b in ocr_results if b['center_y'] > market_y]
        parsed_market = parse_ocr_results(market_ocr, items_db)
        complete = [r for r in parsed_market if r['item_id'] and r['price']]
        if len(complete) >= 3:
            print(f"  OCR 文字辨識成功 ({len(complete)} 組)")
            for r in complete:
                print(f"    [OK] {r['item_name']} = {r['price']}")
            return parsed_market, region, holdings, quota

    # OCR 文字不夠才用圖片比對
    complete_all = [r for r in parsed_for_detect if r['item_id'] and r['price']]
    if len(complete_all) >= 3:
        print(f"  OCR 文字辨識成功 ({len(complete_all)} 組)")
        for r in complete_all:
            if r['item_id'] and r['price']:
                print(f"    [OK] {r['item_name']} = {r['price']}")
        return parsed_for_detect, region, holdings, quota

    # fallback: 圖片比對
    print("  OCR 文字不足，改用圖片比對...")
    card_results = identify_items_by_image(filepath, region)

    if not card_results:
        print("  圖片比對也失敗")
        return parsed_for_detect, region, holdings, quota

    import cv2
    img = cv2.imread(filepath)
    img_h = img.shape[0] if img is not None else 1440

    price_blocks = extract_prices_from_ocr(ocr_results)
    if market_y > 0:
        price_blocks = [p for p in price_blocks if p['center_y'] > market_y]
    print(f"  找到 {len(price_blocks)} 個價格數字")

    match_prices_to_cards(card_results, price_blocks, img_h)

    item_id_to_name = {item['id']: item['name_cn'] for item in items_db}
    results = []
    for card in card_results:
        item_id = card['item_id']
        name = item_id_to_name.get(item_id, '?')
        price = card.get('price')
        score = card['match_score']
        status = "OK" if item_id and price else "INCOMPLETE"
        print(f"    [{status}] {name} = {price or '?'} (圖片:{score:.3f})")
        results.append({
            'ocr_text': f'img_match_{item_id}',
            'item_id': item_id,
            'item_name': name,
            'price': price,
            'confidence': score,
        })

    complete = [r for r in results if r['item_id'] and r['price']]
    print(f"  圖片比對結果: {len(complete)}/{len(results)} 組完整")

    return results, region, holdings, quota


def process_my_prices(filepath):
    """處理一張自己市場的截圖。"""
    global last_f2_region, _completed_count
    my_scan_active.set()
    set_scan_status('scanning_self', None)
    saved_count = 0
    try:
        parsed, region, holdings, quota = scan_with_image_match(filepath)
        if region:
            set_scan_status('scanning_self', region)

        if not parsed:
            print("  未辨識到任何物品或價格")
            return

        # 記錄區域，讓 F3 知道要比對哪個區域
        if region:
            last_f2_region = region
            print(f"  ★ 已鎖定區域: {REGIONS.get(region, region)}，後續 F3 只比對該區域物品")

        region_name = REGIONS.get(region, region) if region else "未知"

        game_date = get_game_date()
        saved = 0
        for item in parsed:
            if item['item_id'] and item['price']:
                upsert_price(item['item_id'], item['price'],
                             game_date=game_date, source='scanner')
                saved += 1
                print(f"  >> {item['item_name']}: {item['price']}")
        saved_count = saved

        # 儲存持有區囤貨
        stockpile_saved = 0
        if holdings and region:
            for h in holdings:
                upsert_stockpile(h['item_id'], h['price'], region, game_date=game_date)
                stockpile_saved += 1
                print(f"  >> [囤貨] {h['item_name']}: {h['price']}")

        # 儲存剩餘配額
        if quota and region:
            upsert_quota(region, quota['remaining'], quota['max'], game_date=game_date)
            print(f"  >> [配額] {region_name} 剩餘 {quota['remaining']}/{quota['max']}")

        print(f"\n  已儲存 {saved} 筆自己的價格 ({region_name})")
        if stockpile_saved:
            print(f"  已記錄 {stockpile_saved} 筆囤貨")
        ensure_flask()
        print(f"  重新整理網頁即可查看")

    except Exception as e:
        print(f"  錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _completed_count += 1
        my_scan_active.clear()
        if saved_count > 0:
            f2_ready.set()  # 通知 worker_f3 可以處理暫存的 F3 截圖了
            if f3_queue.unfinished_tasks > 0:
                # F3 在排隊，狀態交給 worker_f3 接手寫，避免 idle 閃爍
                pass
            else:
                set_scan_status('idle', error='')
        else:
            # F2 沒存入任何價格：f2_ready 保持 clear，F3 繼續等下次 F2
            set_scan_status('idle', error='自己市場掃描未辨識到任何價格，請重新按 F2')
            print("  [!] 本次自己市場掃描未存入任何價格，好友比對將等待下次成功掃描")


def _do_f2_capture():
    """實際執行 F2 截圖並入隊。給 keypress 與 decision thread 共用。"""
    my_scan_active.set()
    f2_ready.clear()
    print(f"\n{'='*50}")
    print(f"[F2] 掃描自己的市場")
    print(f"{'='*50}")
    try:
        filepath = capture_foreground_window()
        print(f"  截圖已儲存: {filepath}")
        f2_queue.put(filepath)
    except Exception as e:
        print(f"  截圖錯誤: {e}")
        my_scan_active.clear()


def _wait_f2_decision_thread():
    """背景 thread：輪詢 f2_decision.json，依結果清 f3_queue + 執行 F2 或取消。"""
    try:
        F2_DECISION_FILE.parent.mkdir(parents=True, exist_ok=True)
        # 清掉殘留檔避免吃到舊決定
        if F2_DECISION_FILE.exists():
            try: F2_DECISION_FILE.unlink()
            except Exception: pass

        timeout = 60.0
        start = time.time()
        while time.time() - start < timeout:
            if F2_DECISION_FILE.exists():
                try:
                    data = json.loads(F2_DECISION_FILE.read_text(encoding='utf-8'))
                except Exception:
                    data = {}
                try: F2_DECISION_FILE.unlink()
                except Exception: pass
                action = data.get('action')
                if action == 'confirm':
                    cleared_queue = 0
                    while True:
                        try:
                            f3_queue.get_nowait()
                            f3_queue.task_done()
                            cleared_queue += 1
                        except Exception:
                            break
                    # 通知 worker_f3 丟棄它已 get 但還沒處理的那張
                    _drop_in_flight_f3.set()
                    print(f"\n  [換區確認] 已清空待辦好友比對 {cleared_queue} 張，並會丟棄處理中的 1 張")
                    clear_pending_f2()
                    f2_pending_lock.clear()
                    _do_f2_capture()
                else:
                    print(f"\n  [換區取消] 保留好友比對暫存")
                    clear_pending_f2()
                    f2_pending_lock.clear()
                return
            time.sleep(0.3)

        # Timeout
        print(f"\n  [換區逾時取消] 60 秒未決定，自動取消")
        clear_pending_f2()
        f2_pending_lock.clear()
    except Exception as e:
        print(f"  [換區 decision thread 錯誤] {e}")
        clear_pending_f2()
        f2_pending_lock.clear()


def scan_my_prices():
    """F2: 立刻截圖；若還有未完成的好友比對，改跳網頁確認窗讓使用者決定。"""
    pending_f3 = f3_queue.unfinished_tasks
    if pending_f3 > 0:
        if f2_pending_lock.is_set():
            print(f"\n  [掃描忽略] 已有換區確認窗等待中")
            return
        f2_pending_lock.set()
        print(f"\n  [等待換區確認] 還有 {pending_f3} 張好友比對未處理，網頁確認窗已彈出")
        set_pending_f2(pending_f3)
        threading.Thread(target=_wait_f2_decision_thread, daemon=True).start()
        return
    _do_f2_capture()


def parse_friend_list(ocr_results, img_width=2560):
    """
    解析好友價格畫面右側的好友列表。
    每行: 好友名稱(含#號) + 價格數字

    Returns:
        List of {'friend_name': str, 'price': int}
    """
    name_blocks = []
    price_blocks = []

    # 只讀取右側好友列表區域，排除左側物品圖的 OCR 雜訊
    x_min = img_width * 0.3  # 好友列表在畫面右側 70%
    # 價格欄在中間；右邊「對比本地區 / 對於持有」百分比欄會被誤讀為 4 位數
    # （例：▲51.1% → 5110），所以價格只抓 x < 0.75*width 的區塊
    price_x_max = img_width * 0.75

    for block in ocr_results:
        text = block['text'].strip()
        # 過濾左側區域的 OCR 雜訊
        if block['center_x'] < x_min:
            continue
        # 好友名稱含有 # 號 (如 "Zenemid#7919")
        if '#' in text and len(text) >= 3:
            name_blocks.append({
                'name': text,
                'center_y': block['center_y'],
                'center_x': block['center_x'],
            })
            continue
        # 價格: 4 位數字 (1000~6000)，只在價格欄 x 範圍內抓
        if block['center_x'] >= price_x_max:
            continue
        match = re.search(r'(\d{4})', text)
        if match:
            val = int(match.group(1))
            if 1000 <= val <= 6000:
                price_blocks.append({
                    'price': val,
                    'center_y': block['center_y'],
                    'center_x': block['center_x'],
                })

    # 按 y 座標配對: 每個名字找最近的價格
    # 好友列表一定由高到低排序，遇到「比前一筆更高」的價格視為 OCR 雜訊（如 ▲51.1% → 5110）
    results = []
    used = set()
    prev_price = None
    for nb in sorted(name_blocks, key=lambda x: x['center_y']):
        # 依 y 由近到遠排序候選，選第一個符合「<= 前一筆」的價格
        candidates = []
        for i, pb in enumerate(price_blocks):
            if i in used:
                continue
            dy = abs(pb['center_y'] - nb['center_y'])
            if dy < 80:
                candidates.append((dy, i, pb))
        candidates.sort(key=lambda x: x[0])

        chosen = None
        chosen_idx = -1
        for dy, i, pb in candidates:
            if prev_price is None or pb['price'] <= prev_price:
                chosen = pb
                chosen_idx = i
                break

        if chosen is not None:
            used.add(chosen_idx)
            prev_price = chosen['price']
            results.append({
                'friend_name': nb['name'],
                'price': chosen['price'],
            })
            print(f"    {nb['name']}: {chosen['price']}")
        else:
            print(f"    {nb['name']}: (未找到價格)")

    return results


def process_friend_prices(filepath):
    """處理一張好友價格的截圖。"""
    global _completed_count
    # 還沒辨識物品前不指定區域，避免 stale last_f2_region 在錯區域畫 placeholder
    set_scan_status('scanning_friend', None)
    try:
        # Step 1: 圖片比對辨識左側大物品圖 (限定 F2 掃到的區域)
        region_hint = last_f2_region
        if region_hint:
            print(f"  限定比對區域: {REGIONS.get(region_hint, region_hint)}")
        item_id, score, region = identify_friend_item(filepath, region_hint=region_hint)
        if region:
            set_scan_status('scanning_friend', region)
        if not item_id:
            print("  無法辨識物品圖片")
            return

        items_db = get_all_items()
        item_name = next((it['name_cn'] for it in items_db if it['id'] == item_id), '?')
        region_name = REGIONS.get(region, region) if region else "未知"
        print(f"  辨識物品: {item_name} (item_{item_id}, {region_name})")

        # Step 2: OCR 讀取好友名稱 + 價格
        print("  OCR 辨識好友列表中...")
        ocr_results = recognize(filepath)
        print(f"  OCR 找到 {len(ocr_results)} 個文字區塊")

        # 取得圖片寬度用於過濾左側雜訊
        import cv2
        img = cv2.imread(filepath)
        img_width = img.shape[1] if img is not None else 2560

        friend_list = parse_friend_list(ocr_results, img_width=img_width)
        if not friend_list:
            print("  未辨識到好友價格")
            return

        # Step 3: 清除該物品舊的好友價格，再儲存新的
        game_date = get_game_date()
        delete_friend_prices_for_item(item_id, game_date)
        saved = 0
        for entry in friend_list:
            upsert_friend_price(item_id, entry['price'],
                                friend_name=entry['friend_name'],
                                game_date=game_date, source='scanner')
            saved += 1

        print(f"\n  已儲存 {saved} 筆好友價格 - {item_name} ({region_name})")
        ensure_flask()
        print(f"  重新整理網頁的「利潤比對」頁面即可查看比較結果")

    except Exception as e:
        print(f"  錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _completed_count += 1
        # 若 F3 佇列還有待處理的，保持 scanning_friend 狀態；否則回 idle
        if f3_queue.unfinished_tasks > 1:
            set_scan_status('scanning_friend', last_f2_region)
        else:
            set_scan_status('idle')


def scan_friend_prices():
    """F3: 立刻截圖，丟進佇列背景處理。"""
    print(f"\n{'='*50}")
    print(f"[F3] 掃描好友的市場價格")
    print(f"{'='*50}")

    try:
        filepath = capture_foreground_window()
        print(f"  截圖已儲存: {filepath}")
        f3_queue.put(filepath)
    except Exception as e:
        print(f"  截圖錯誤: {e}")



def watchdog_heartbeat(grace=30, timeout=15):
    """網頁每 2 秒 POST /api/heartbeat 更新 heartbeat.json。
    若超過 `timeout` 秒沒心跳（啟動 `grace` 秒後開始檢查），視為網頁已關閉，觸發退出。"""
    # 清掉舊 heartbeat，避免用上次殘留值
    try:
        if HEARTBEAT_FILE.exists():
            HEARTBEAT_FILE.unlink()
    except Exception:
        pass
    time.sleep(grace)
    while not _shutdown_event.is_set():
        try:
            if HEARTBEAT_FILE.exists():
                age = time.time() - HEARTBEAT_FILE.stat().st_mtime
                if age > timeout:
                    print(f"\n網頁已關閉超過 {int(age)} 秒，自動結束掃描器...")
                    _shutdown_event.set()
                    return
        except Exception:
            pass
        time.sleep(2)


def quit_hotkey_listener():
    """Ctrl+Shift+Q 熱鍵 → 跳確認視窗 → 設 shutdown event。"""
    while not _shutdown_event.is_set():
        keyboard.wait('ctrl+shift+q')
        if _shutdown_event.is_set():
            return
        MB_YESNO = 0x4
        MB_ICONQUESTION = 0x20
        MB_TOPMOST = 0x40000
        IDYES = 6
        result = ctypes.windll.user32.MessageBoxW(
            0, "確定要關閉終末地追蹤器嗎？", "終末地追蹤器",
            MB_YESNO | MB_ICONQUESTION | MB_TOPMOST,
        )
        if result == IDYES:
            _shutdown_event.set()
            return
        print("  取消關閉，繼續等待快捷鍵...")


def worker_f2():
    """背景執行緒：依序處理 F2 佇列中的截圖。"""
    while True:
        filepath = f2_queue.get()
        if filepath is None:
            break
        print(f"\n  [F2 處理中] {os.path.basename(filepath)}")
        process_my_prices(filepath)
        f2_queue.task_done()


def worker_f3():
    """背景執行緒：依序處理好友比對佇列中的截圖。自己市場掃描必須成功完成過才會處理。"""
    while True:
        # 換區確認窗開著時，不要拉新 item 出來處理
        while f2_pending_lock.is_set():
            time.sleep(0.3)

        filepath = f3_queue.get()
        if filepath is None:
            break
        # 保險延遲：若兩個熱鍵幾乎同時按下，給對方 callback 機會 set 旗標
        time.sleep(0.15)
        if not f2_ready.is_set():
            print(f"\n  [好友比對 暫存] {os.path.basename(filepath)} 等待 自己市場掃描 完成...")
            # 自己市場掃描中：不寫狀態，讓它自己的進度顯示繼續呈現
            # 從未掃描過自己市場：寫 banner 提示
            if not my_scan_active.is_set() and last_f2_region is None:
                set_scan_status('idle', error='好友比對截圖已暫存，請先按 F2 掃描自己的市場')
                wrote_pending_error = True
            else:
                wrote_pending_error = False
            f2_ready.wait()
            print(f"  [好友比對 繼續] 自己市場掃描完成，開始處理")
            if wrote_pending_error:
                set_scan_status('idle', error='')

        # 等任何換區確認窗結束（user 可能在 wait 期間按了新 F2）
        while f2_pending_lock.is_set():
            time.sleep(0.3)

        # 換區確認後通知丟棄這張
        if _drop_in_flight_f3.is_set():
            _drop_in_flight_f3.clear()
            print(f"\n  [好友比對 已捨棄] {os.path.basename(filepath)}（換區）")
            f3_queue.task_done()
            continue

        print(f"\n  [好友比對 處理中] {os.path.basename(filepath)}")
        process_friend_prices(filepath)
        f3_queue.task_done()


def main():
    init_db()

    print("=" * 50)
    print("  彈性物資價格掃描器")
    print("=" * 50)
    print()
    print("  F2  = 掃描自己的市場價格")
    print("  F3  = 掃描好友的市場價格")
    print("  Ctrl+Shift+Q = 結束程式")
    print()
    print("  * 區域自動偵測（不需手動切換）")
    print("  * 請確保遊戲視窗在最前面再按快捷鍵")
    print("  * 可連續按鍵截圖，會自動排隊處理")
    print("  * F3 會自動學習物品圖片，辨識會越來越準")
    print()
    print(f"  遊戲日期: {get_game_date()}")
    print()

    # 啟動 Flask
    ensure_flask()
    set_scan_status('idle', error='')
    # 等 Flask 起來再開瀏覽器（避免第一次連線失敗）
    time.sleep(1.5)
    try:
        webbrowser.open('http://127.0.0.1:5000/compare')
    except Exception:
        pass
    print()

    # Pre-load OCR engine
    print("  正在載入 OCR 引擎（首次較慢）...")
    from ocr.engine import get_ocr
    get_ocr()
    print("  OCR 引擎已就緒！")
    print()
    print("  等待中... 請在遊戲市場畫面按 F2 或 F3")
    print()

    # 啟動背景處理執行緒
    t2 = threading.Thread(target=worker_f2, daemon=True)
    t3 = threading.Thread(target=worker_f3, daemon=True)
    t2.start()
    t3.start()

    keyboard.on_press_key('f2', lambda _: scan_my_prices())
    keyboard.on_press_key('f3', lambda _: scan_friend_prices())

    # 熱鍵監聽：Ctrl+Shift+Q 觸發關閉
    # （心跳自動關閉模式已移除，因瀏覽器對背景分頁 throttle 會造成誤判）
    threading.Thread(target=quit_hotkey_listener, daemon=True).start()

    _shutdown_event.wait()

    # 清理：用 taskkill /F /T 殺整個 Flask 行程樹（debug mode 的 reloader 子行程也要殺）
    if flask_process and flask_process.poll() is None:
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(flask_process.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            try:
                flask_process.kill()
            except Exception:
                pass
    print("\n程式結束。")

    # 關掉 scanner 自己的 console 視窗
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    except Exception:
        pass


if __name__ == '__main__':
    main()
