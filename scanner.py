"""
背景掃描程式 - 快捷鍵截圖 + OCR 自動辨識價格
F2: 掃描自己的市場價格（自動截取遊戲視窗）
F3: 掃描好友的市場價格
ESC: 結束程式

辨識方式：圖片比對確認物品 + OCR 讀取價格
"""
import os
import re
import sys
import time
import ctypes
import ctypes.wintypes
import tempfile
import subprocess
import threading
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
from data.items import REGION_QUOTA
from ocr.engine import recognize
from ocr.parser import parse_ocr_results
from ocr.image_matcher import identify_items_by_image, get_card_positions, identify_friend_item


# State
flask_process = None
f2_queue = Queue()
f3_queue = Queue()
last_f2_region = None  # F2 掃完後記錄區域，F3 只在該區域內比對


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


def parse_remaining_quota(ocr_results, region, market_y):
    """
    從 OCR 結果找出剩餘配額數字。
    遊戲市場畫面頂端會顯示類似「65/130」或「320/960」的配額數字。
    只看市場標題上方區域（market_y 之上），避免被價格數字干擾。
    """
    if not region or region not in REGION_QUOTA:
        return None
    max_quota = REGION_QUOTA[region]['max']
    daily = REGION_QUOTA[region]['daily']

    search_area = [b for b in ocr_results if market_y <= 0 or b['center_y'] < market_y]

    pattern_slash = re.compile(r'(\d{1,4})\s*[/／]\s*(\d{2,4})')
    best = None
    for block in search_area:
        text = block['text']
        for m in pattern_slash.finditer(text):
            remaining, total = int(m.group(1)), int(m.group(2))
            if total == max_quota and 0 <= remaining <= max_quota:
                if best is None or block['center_y'] < best['y']:
                    best = {'remaining': remaining, 'max': total, 'y': block['center_y']}

    if best:
        print(f"  剩餘配額: {best['remaining']}/{best['max']}")
        return {'remaining': best['remaining'], 'max': best['max']}

    pattern_num = re.compile(r'(?<!\d)(\d{1,4})(?!\d)')
    for block in search_area:
        for m in pattern_num.finditer(block['text']):
            n = int(m.group(1))
            if 0 <= n <= max_quota and (n % daily == 0 or n == max_quota):
                print(f"  剩餘配額 (fallback): {n}/{max_quota}")
                return {'remaining': n, 'max': max_quota}

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
    quota = parse_remaining_quota(ocr_results, region, market_y)

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
    global last_f2_region
    try:
        parsed, region, holdings, quota = scan_with_image_match(filepath)

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


def scan_my_prices():
    """F2: 立刻截圖，丟進佇列背景處理。"""
    print(f"\n{'='*50}")
    print(f"[F2] 掃描自己的市場")
    print(f"{'='*50}")

    try:
        filepath = capture_foreground_window()
        print(f"  截圖已儲存: {filepath}")
        f2_queue.put(filepath)
    except Exception as e:
        print(f"  截圖錯誤: {e}")


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
        # 價格: 4 位數字 (1000~6000)，排除百分比數字 (如 481.9% → 481)
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
    results = []
    used = set()
    for nb in sorted(name_blocks, key=lambda x: x['center_y']):
        best_price = None
        best_dist = float('inf')
        best_idx = -1
        for i, pb in enumerate(price_blocks):
            if i in used:
                continue
            dy = abs(pb['center_y'] - nb['center_y'])
            if dy < best_dist and dy < 80:
                best_dist = dy
                best_price = pb
                best_idx = i
        if best_price is not None:
            used.add(best_idx)
            results.append({
                'friend_name': nb['name'],
                'price': best_price['price'],
            })
            print(f"    {nb['name']}: {best_price['price']}")
        else:
            print(f"    {nb['name']}: (未找到價格)")

    return results


def process_friend_prices(filepath):
    """處理一張好友價格的截圖。"""
    try:
        # Step 1: 圖片比對辨識左側大物品圖 (限定 F2 掃到的區域)
        region_hint = last_f2_region
        if region_hint:
            print(f"  限定比對區域: {REGIONS.get(region_hint, region_hint)}")
        item_id, score, region = identify_friend_item(filepath, region_hint=region_hint)
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
    """背景執行緒：依序處理 F3 佇列中的截圖。"""
    while True:
        filepath = f3_queue.get()
        if filepath is None:
            break
        print(f"\n  [F3 處理中] {os.path.basename(filepath)}")
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
    print("  ESC = 結束程式")
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

    while True:
        keyboard.wait('esc')
        MB_YESNO = 0x4
        MB_ICONQUESTION = 0x20
        MB_TOPMOST = 0x40000
        IDYES = 6
        result = ctypes.windll.user32.MessageBoxW(
            0, "確定要關閉終末地追蹤器嗎？", "終末地追蹤器",
            MB_YESNO | MB_ICONQUESTION | MB_TOPMOST,
        )
        if result == IDYES:
            break
        print("  取消關閉，繼續等待快捷鍵...")
    print("\n程式結束。")


if __name__ == '__main__':
    main()
