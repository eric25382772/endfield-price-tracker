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
import socket
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
    delete_friend_prices_for_item, upsert_stockpile, upsert_quota,
    get_friend_name_alias, set_friend_name_alias
)
from data.items import REGION_QUOTA, get_region_quota
from ocr.engine import recognize, recognize_crop
from ocr.parser import parse_ocr_results
from ocr.image_matcher import identify_items_by_image, get_card_positions, identify_friend_item


# State
flask_process = None
f2_queue = Queue()
f3_queue = Queue()
f4_queue = Queue()  # F4：專掃「目前持有」囤貨，獨立於 F2/F3 狀態機
last_f2_region = None  # F2 掃完後記錄區域，F3 只在該區域內比對
my_scan_active = threading.Event()  # F2 辨識中，F3 需等待避免畫面混淆
f2_ready = threading.Event()  # F2 已成功完成過至少一次且目前未在跑，F3 才能處理

SCAN_STATUS_FILE = Path(__file__).parent / 'data' / 'scan_status.json'
HEARTBEAT_FILE = Path(__file__).parent / 'data' / 'heartbeat.json'
# 網頁全部關閉時，Flask 端寫此旗標；scanner 讀到就結束整組程式
SHUTDOWN_FILE = Path(__file__).parent / 'data' / 'shutdown.flag'
# 記錄本輪 spawn 的 PID（scanner 自己 + Flask），供下次啟動清理沒關乾淨的殘留
PID_REGISTRY_FILE = Path(__file__).parent / 'data' / 'scanner.pids.json'
LOG_FILE = Path(__file__).parent / 'data' / 'scanner.log'
# F3 好友掃描的原始 OCR 診斷 log：每列原文/座標/信心，方便事後查名字/價格認錯
FRIEND_OCR_DEBUG_LOG = Path(__file__).parent / 'data' / 'friend_ocr_debug.log'
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


def _setup_output():
    """pythonw 啟動時沒有 console，sys.stdout/stderr 為 None，print 會直接炸。
    導向 data/scanner.log，讓隱藏視窗模式仍能事後查 F4/OCR 有沒有出錯。"""
    if sys.stdout is not None:
        return
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        f = open(LOG_FILE, 'a', encoding='utf-8', buffering=1)
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass


def _register_pid(pid):
    """把本專案 spawn 的 PID 記進登記檔，供下次啟動 reap_leftover_instances 清理。"""
    try:
        pids = []
        if PID_REGISTRY_FILE.exists():
            pids = json.loads(PID_REGISTRY_FILE.read_text(encoding='utf-8'))
        if pid not in pids:
            pids.append(pid)
        PID_REGISTRY_FILE.write_text(json.dumps(pids), encoding='utf-8')
    except Exception:
        pass


def _pid_is_python(pid):
    """確認 PID 仍存活且是 python/pythonw，避免 PID 重用時誤殺別的程式。"""
    try:
        out = subprocess.run(
            ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.lower()
        return 'python.exe' in out or 'pythonw.exe' in out
    except Exception:
        return False


def _kill_tree(pid):
    """用 taskkill /F /T 殺整個行程樹（含 Flask reloader 子行程）。"""
    try:
        subprocess.run(
            ['taskkill', '/F', '/T', '/PID', str(pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def _pid_on_port(port):
    """回傳正在 LISTEN 指定埠的 PID（找不到回 None）。"""
    try:
        out = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
        for line in out.splitlines():
            parts = line.split()
            # 例：TCP  127.0.0.1:5000  0.0.0.0:0  LISTENING  6940
            if len(parts) >= 5 and parts[3] == 'LISTENING' and parts[1].endswith(f':{port}'):
                return int(parts[-1])
    except Exception:
        pass
    return None


def reap_leftover_instances():
    """啟動時自我修復：清掉上一輪沒關乾淨的殘留。
    來源＝登記檔記錄的 PID ＋ 目前占用 5000 埠者；只碰 python/pythonw，
    且 5000 埠為本程式專用，不會誤傷其他專案（如 MT5）。"""
    self_pid = os.getpid()
    victims = set()
    try:
        if PID_REGISTRY_FILE.exists():
            for pid in json.loads(PID_REGISTRY_FILE.read_text(encoding='utf-8')):
                if int(pid) != self_pid:
                    victims.add(int(pid))
    except Exception:
        pass
    port_pid = _pid_on_port(5000)
    if port_pid and port_pid != self_pid:
        victims.add(port_pid)
    killed = []
    for pid in victims:
        if _pid_is_python(pid):  # 驗證是 python/pythonw 才殺，避開 PID 重用誤傷
            _kill_tree(pid)
            killed.append(pid)
    if killed:
        print(f"  已清理上一輪未關乾淨的殘留進程: {killed}")
    # 登記檔重置為只含自己這一輪
    try:
        PID_REGISTRY_FILE.write_text(json.dumps([self_pid]), encoding='utf-8')
    except Exception:
        pass


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
        creationflags=subprocess.CREATE_NO_WINDOW,  # 不顯示 Flask 的黑視窗
    )
    _register_pid(flask_process.pid)  # 記下 Flask PID，供下次啟動清理
    print("  Flask 已自動啟動 (127.0.0.1:5000)")


def wait_for_flask(timeout=60):
    """輪詢 127.0.0.1:5000 直到 Flask 開始接受連線。回傳是否在時限內就緒。
    取代舊的固定 sleep(1.5)：第一次啟動 Flask 冷載入較久，固定等待會讓瀏覽器先開到『拒絕連線』。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', 5000), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def wait_for_web_page(timeout=30):
    """輪詢 /api/web_ready 直到網頁真的連上（SSE 已建立）。回傳是否在時限內就緒。

    webbrowser.open() 只是把瀏覽器叫起來就回傳，瀏覽器冷啟動＋渲染還要好幾秒；
    直接關掉提示視窗會出現「視窗沒了但頁面還沒出現」的空窗。逾時仍會放行，
    避免瀏覽器開不起來時視窗一直掛著。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            import urllib.request
            with urllib.request.urlopen(
                    'http://127.0.0.1:5000/api/web_ready', timeout=1) as r:
                if json.loads(r.read().decode('utf-8')).get('ready'):
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def show_splash():
    """啟動時彈一個無邊框提示視窗（含實心進度綠條），讓使用者知道正在開啟、不是沒反應。
    在獨立執行緒跑自己的 Tk mainloop，不擋主執行緒後續載入 OCR；綠條在 tick 裡平滑往前爬向
    目標值（ease-out），所以就算某階段等較久也是持續前進，不會死在原地、也不是跑馬燈。
    回傳 (update, close)：update(text, percent) 換文字並設目標進度、close() 立即關閉視窗。"""
    msg_q = Queue()
    ready = threading.Event()

    def run():
        try:
            import tkinter as tk
            from tkinter import ttk
        except Exception:
            ready.set()
            return
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes('-topmost', True)
        w, h = 380, 150
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        root.configure(bg='#1b1b1f')
        tk.Label(root, text='終末地彈性物資價格追蹤器', fg='#e6c86e', bg='#1b1b1f',
                 font=('Microsoft JhengHei', 12, 'bold')).pack(pady=(26, 8))
        status = tk.Label(root, text='正在啟動…', fg='#dddddd', bg='#1b1b1f',
                          font=('Microsoft JhengHei', 10))
        status.pack()
        pb = ttk.Progressbar(root, mode='determinate', maximum=100, length=300)
        pb.pack(pady=18)
        state = {'target': 8.0, 'value': 0.0, 'closing': False}

        def tick():
            # 收到關閉訊號就立刻收掉，不再等進度條爬到 100%（網頁已開就不該再佔著畫面）
            if state['closing']:
                root.destroy()
                return
            t, v = state['target'], state['value']
            if v < t:
                v = min(t, v + max(0.35, (t - v) * 0.06))
                state['value'] = v
                pb['value'] = v
            root.after(30, tick)

        def poll():
            try:
                while True:
                    item = msg_q.get_nowait()
                    if item is None:
                        state['closing'] = True
                        state['target'] = 100.0
                    else:
                        text, percent = item
                        if text is not None:
                            status.config(text=text)
                        if percent is not None:
                            state['target'] = float(percent)
            except Exception:
                pass
            root.after(80, poll)

        root.after(30, tick)
        root.after(80, poll)
        ready.set()
        root.mainloop()

        # mainloop 結束後必做的收尾（否則會 Tcl_AsyncDelete abort 整個進程）：
        # root 與它 after() 註冊的 tick/poll 回呼互相參照成環，refcount 收不掉，
        # 會殘留到主執行緒的循環 GC 才回收；Tk 物件一旦在「非建立它的執行緒」被
        # finalize，就會丟「async handler deleted by the wrong thread」直接 abort。
        # 解法：在這條（建立 Tk 的）執行緒上主動丟參照 + gc，讓 Tkapp 在此處釋放。
        try:
            root.quit()
        except Exception:
            pass
        root = status = pb = None
        tick = poll = None
        import gc
        gc.collect()

    threading.Thread(target=run, daemon=True).start()
    ready.wait(timeout=5)
    return (lambda text=None, percent=None: msg_q.put((text, percent))), (lambda: msg_q.put(None))


def get_foreground_window_rect():
    """Get the foreground window's CLIENT area (純遊戲畫面) in screen coords.

    用 client area 而非整個 window rect：視窗模式下才能排除標題列／邊框，
    讓卡位座標的 2560x1440 比例縮放對得上。全螢幕無邊框時 client == window，
    尺寸與行為完全不變。"""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()

    # client area 尺寸（left/top 恆為 0，不含標題列與邊框）
    client = ctypes.wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client))

    # 把 client 左上角 (0,0) 轉成螢幕座標，得到擷取起點
    pt = ctypes.wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))

    # Get window title for logging
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    return {
        'left': pt.x,
        'top': pt.y,
        'width': client.right - client.left,
        'height': client.bottom - client.top,
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
    region = None
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

        # 囤貨（目前持有）已移至 F4 專鍵處理，F2 不再代勞

        # 儲存剩餘配額
        if quota and region:
            upsert_quota(region, quota['remaining'], quota['max'], game_date=game_date)
            print(f"  >> [配額] {region_name} 剩餘 {quota['remaining']}/{quota['max']}")

        print(f"\n  已儲存 {saved} 筆自己的價格 ({region_name})")
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
                # 帶上剛掃到的地區，網頁完成時才能自動跳到該分頁
                set_scan_status('idle', region=region, error='')
        else:
            # F2 沒存入任何價格：f2_ready 保持 clear，F3 繼續等下次 F2
            set_scan_status('idle', region=region, error='自己市場掃描未辨識到任何價格，請重新按 F2')
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


# 幾乎不會出現在真實玩家暱稱、卻常見於 OCR 亂碼的符號
_NAME_JUNK = set("|\\=^~`[]{}<>")


def _has_cjk(s):
    """字串是否含中（漢字）／日（平假名・片假名）／韓（諺文）文字。"""
    for ch in s:
        o = ord(ch)
        if (0x3040 <= o <= 0x30FF or   # 平/片假名
                0x3400 <= o <= 0x9FFF or   # 漢字（含擴充 A）
                0xAC00 <= o <= 0xD7A3):    # 韓文音節
            return True
    return False


def _has_kana_or_hangul(s):
    """含日文假名或韓文諺文（不含漢字）。
    用來判斷「低信心名」是否真的是日韓名 —— 只有含假名/諺文才該丟去日韓 reader 重讀；
    純漢字的低信心名（例：罕見字『苜蓿米』被讀錯）本來就是中文，丟日韓只會更糟。"""
    for ch in s:
        o = ord(ch)
        if (0x3040 <= o <= 0x30FF or   # 平/片假名
                0xAC00 <= o <= 0xD7A3):    # 韓文音節
            return True
    return False


def _looks_garbled(name):
    """好友名（含 #tag）去掉編號後，含亂碼符號或有效字元比例過低 → 視為認錯。
    isalnum() 在 Python 對中日韓文字也回 True，所以中/日/韓/英名字都算有效。"""
    base = re.sub(r'#\d{3,4}$', '', name).strip().replace(' ', '')
    if not base:
        return True
    if any(ch in _NAME_JUNK for ch in base):
        return True
    # 真實暱稱至少有一個「字母」（英數中日韓的字，isalpha 對中日韓也回 True）。
    # 只剩數字／符號（例：片假名「アニマ」被繁中 reader 誤讀成「7_7」）視為認錯，
    # 才會進日韓回退；否則 0.6 比例門檻會放行而永遠跳過回退。
    if not any(ch.isalpha() for ch in base):
        return True
    # 片假名／韓文常被繁中 reader 讀成「漢字＋ASCII 數字/符號」的混雜串
    # （例：わっち→枸51、らぷらす→5.3:5寸）。CJK 文字與 ASCII 非字母混在一起 → 視為認錯。
    # 真名通常同一語系（全漢字 / 全假名 / 全諺文 / 全英），不會 CJK 夾 ASCII 數字符號；
    # 純英數名（Fox0nLy）不含 CJK，不受影響。
    if _has_cjk(base) and any(ch.isascii() and not ch.isalpha() for ch in base):
        return True
    valid = sum(1 for ch in base if ch.isalnum())
    return valid / len(base) < 0.6


def _canonicalize_friend_name(raw, bbox, image, conf=None):
    """把一個好友名 raw 正規化成正解。
    1. alias 表命中 → 直接用（跳過日韓回退，這就是「越用越快」的來源）
    2. 看起來是亂碼、或繁中 reader 信心過低 → 裁切該名字區塊，回退跑日文、韓文
    3. 都沒改善 → 原樣返回（中英名字本來就在這條快路上）
    """
    learned = get_friend_name_alias(raw)
    if learned:
        return learned
    # 觸發日韓回退的兩種情形：
    #   a) 亂碼（7_7、枸51、5.3:5寸 這種）
    #   b) 繁中信心過低「且名字含假名/諺文」（例：ろ一さ conf=0.53，ー 被讀成漢字一）。
    #      —— 必須有假名/諺文才丟去日韓，否則純漢字的罕見字中文名（苜蓿米）會被換成日文亂碼。
    low_conf = (conf is not None and conf < 0.6 and _has_kana_or_hangul(raw))
    garbled = _looks_garbled(raw)
    if not garbled and not low_conf:
        return raw
    if image is None or not bbox:
        return raw
    m = re.search(r'(#\d{3,4})$', raw.strip())
    tag = m.group(1) if m else ''
    digits = tag.lstrip('#')
    best = None
    for langs in (('ja', 'en'), ('ko', 'en')):
        text, conf = recognize_crop(image, bbox, langs)
        if not text:
            continue
        # 回退結果只取「名字」部分，編號一律用繁中讀到的 tag（數字本來就好認）。
        # 砍掉尾端的編號（含 # 被誤判成 井／＃ 或省略、夾雜空白的情況）
        name_part = text
        cut = re.search(r'[#＃井]?\s*' + re.escape(digits) + r'\s*$', name_part) if digits else None
        if cut:
            name_part = name_part[:cut.start()]
        else:
            name_part = re.split(r'[#＃0-9]', name_part, 1)[0]
        name_part = re.sub(r'[\s#＃井|/=^~`\[\]{}<>]+$', '', name_part).strip()
        if not name_part:
            continue
        cand = name_part + tag
        if _looks_garbled(cand):
            continue
        if best is None or conf > best[1]:
            best = (cand, conf)
    if best:
        # 只在「原本是亂碼」或「回退比繁中更有把握」時才取代，避免把對的中文名換掉
        if garbled or best[1] > (conf or 0):
            set_friend_name_alias(raw, best[0], source='ocr_fallback')
            print(f"    [日韓回退] {raw} → {best[0]} (conf {best[1]:.2f})")
            return best[0]
    return raw


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
                'bbox': block['bbox'],
                'conf': block.get('confidence', 0.0),
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
                'bbox': nb['bbox'],
                'name_conf': nb.get('conf', 0.0),
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
        debug_rows = []
        for entry in friend_list:
            name = _canonicalize_friend_name(entry['friend_name'], entry.get('bbox'), img,
                                             conf=entry.get('name_conf'))
            upsert_friend_price(item_id, entry['price'],
                                friend_name=name,
                                game_date=game_date, source='scanner')
            saved += 1
            debug_rows.append((entry['friend_name'], name, entry['price']))

        # 診斷 log：原始 OCR + 配對/正規化結果，方便事後查名字/價格認錯
        try:
            from datetime import datetime as _dt
            with open(FRIEND_OCR_DEBUG_LOG, 'a', encoding='utf-8') as _f:
                _f.write(f"\n===== {_dt.now():%Y-%m-%d %H:%M:%S}  item_{item_id} {item_name} ({region_name}) =====\n")
                _f.write("-- 原始 OCR 區塊（依 y, x 排序）--\n")
                for b in sorted(ocr_results, key=lambda x: (x['center_y'], x['center_x'])):
                    _f.write(f"   text={b['text']!r:24} x={b['center_x']:.0f} y={b['center_y']:.0f} conf={b['confidence']:.2f}\n")
                _f.write("-- 配對結果（原讀名 → 正規化名 = 價格）--\n")
                for raw_name, name, price in debug_rows:
                    _f.write(f"   {raw_name!r} -> {name!r} = {price}\n")
        except Exception as _e:
            print(f"  [診斷 log 失敗] {_e}")

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



def process_stockpile(filepath):
    """F4: 只辨識「目前持有」區並儲存囤貨（與 F2 市場掃描分離）。"""
    global _completed_count
    set_scan_status('scanning_stockpile', None)
    try:
        print("  OCR 辨識中...")
        ocr_results = recognize(filepath)
        print(f"  OCR 找到 {len(ocr_results)} 個文字區塊")
        items_db = get_all_items()

        # 找「市場」標題的 y，持有區在它上方
        market_y = 0
        for block in ocr_results:
            if '市場' in block['text']:
                market_y = block['center_y']
                break

        holdings = parse_holding_area(ocr_results, market_y, items_db)
        if not holdings:
            print("  未辨識到持有中的囤貨")
            set_scan_status('idle', error='未辨識到「目前持有」，請確認畫面停在物資調度頁再按 F4')
            return

        region = detect_region(holdings)
        region_name = REGIONS.get(region, region) if region else "未知"
        if region:
            set_scan_status('scanning_stockpile', region)

        game_date = get_game_date()
        saved = 0
        for h in holdings:
            r = region
            if not r:
                # 保險：無法整體判斷區域時，用該物品自己的區域
                item = next((it for it in items_db if it['id'] == h['item_id']), None)
                r = item['region'] if item else None
            if not r:
                continue
            upsert_stockpile(h['item_id'], h['price'], r, game_date=game_date)
            saved += 1
            print(f"  >> [囤貨] {h['item_name']}: {h['price']}")

        if saved:
            print(f"\n  已記錄 {saved} 筆囤貨 ({region_name})")
            ensure_flask()
            print(f"  重新整理網頁即可查看")
            set_scan_status('idle', error='')
        else:
            set_scan_status('idle', error='囤貨辨識到但無法判斷區域，請重試')

    except Exception as e:
        print(f"  錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _completed_count += 1
        set_scan_status('idle')


def scan_stockpile():
    """F4: 立刻截圖，丟進佇列背景處理囤貨。"""
    print(f"\n{'='*50}")
    print(f"[F4] 掃描目前持有（囤貨）")
    print(f"{'='*50}")
    try:
        filepath = capture_foreground_window()
        print(f"  截圖已儲存: {filepath}")
        f4_queue.put(filepath)
    except Exception as e:
        print(f"  截圖錯誤: {e}")


def watchdog_web_closed():
    """Flask 端偵測到網頁全部關閉會寫 shutdown.flag，讀到就觸發整組收工。"""
    while not _shutdown_event.is_set():
        try:
            if SHUTDOWN_FILE.exists():
                print("\n網頁已關閉，自動結束掃描器...")
                _shutdown_event.set()
                return
        except Exception:
            pass
        time.sleep(1)


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


def worker_f4():
    """背景執行緒：依序處理 F4 佇列中的囤貨截圖。獨立於 F2/F3 狀態機。"""
    while True:
        filepath = f4_queue.get()
        if filepath is None:
            break
        print(f"\n  [F4 處理中] {os.path.basename(filepath)}")
        process_stockpile(filepath)
        f4_queue.task_done()


def main():
    _setup_output()  # pythonw（無 console）時把輸出導到 log，避免 print 崩潰

    # 提示視窗最先建立：後面的 init_db／Flask／OCR 在乾淨機器上都可能慢，
    # 晚一步建立就會讓人以為程式沒反應（首次啟動尤其明顯）
    update_splash, close_splash = show_splash()

    init_db()

    # 清掉上一輪殘留的收工旗標，避免一啟動就被誤判關閉
    try:
        if SHUTDOWN_FILE.exists():
            SHUTDOWN_FILE.unlink()
    except Exception:
        pass

    # 自我修復：清掉上一輪沒關乾淨的殘留實例，再往下綁 5000 埠。
    # 「清掉再開」而非「已在執行就拒絕」，確保使用者永遠不會被卡在外面。
    reap_leftover_instances()

    print("=" * 50)
    print("  彈性物資價格掃描器")
    print("=" * 50)
    print()
    print("  F2  = 掃描自己的市場價格")
    print("  F3  = 掃描好友的市場價格")
    print("  F4  = 掃描目前持有（囤貨）")
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
    update_splash('正在啟動伺服器…', 20)
    ensure_flask()
    set_scan_status('idle', error='')
    # 輪詢等 Flask 真的能連了再開瀏覽器（第一次冷載入較久，固定等待會開到『拒絕連線』）
    update_splash('正在開啟網頁…', 45)
    wait_for_flask(60)
    try:
        webbrowser.open('http://127.0.0.1:5000/compare')
    except Exception:
        pass
    # 等網頁真的連上再收視窗：open() 只是把瀏覽器叫起來就回傳，
    # 立刻關會變成「視窗沒了但頁面還沒出現」
    update_splash('正在開啟網頁…', 75)
    wait_for_web_page(30)
    close_splash()
    print()

    # 熱鍵與背景執行緒先掛上，讓網頁一出現就真的能按 F2。
    # OCR 還在預載時按也沒關係：截圖會先進佇列，引擎就緒後照常處理。
    t2 = threading.Thread(target=worker_f2, daemon=True)
    t3 = threading.Thread(target=worker_f3, daemon=True)
    t4 = threading.Thread(target=worker_f4, daemon=True)
    t2.start()
    t3.start()
    t4.start()

    keyboard.on_press_key('f2', lambda _: scan_my_prices())
    keyboard.on_press_key('f3', lambda _: scan_friend_prices())
    keyboard.on_press_key('f4', lambda _: scan_stockpile())

    # 熱鍵監聽：Ctrl+Shift+Q 觸發關閉
    threading.Thread(target=quit_hotkey_listener, daemon=True).start()
    # 關網頁自動收工：Flask 端偵測分頁全關會寫 shutdown.flag（SSE 長連線，不受背景 throttle 影響）
    threading.Thread(target=watchdog_web_closed, daemon=True).start()

    # Pre-load OCR engine：熱鍵此時已可用，這段純粹先暖機讓第一次掃描不用等
    print("  正在載入 OCR 引擎（首次較慢）...")
    from ocr.engine import get_ocr
    try:
        get_ocr()
        print("  OCR 引擎已就緒！")
        print()
        print("  等待中... 請在遊戲市場畫面按 F2 或 F3")
        print()
        _shutdown_event.wait()
    except Exception:
        # pythonw 無 console 時未捕捉例外會靜默結束、留下孤兒 Flask。
        # 這裡明確記錄堆疊，方便事後查崩因（原生層崩潰仍不留 Python 堆疊，靠下次 reap 收拾）。
        import traceback
        print("  [主流程例外] 掃描器即將結束，堆疊如下：")
        traceback.print_exc()
    finally:
        # 收工：無論正常關閉或例外，都殺整個 Flask 行程樹（debug reloader 子行程也要殺）
        if flask_process and flask_process.poll() is None:
            _kill_tree(flask_process.pid)
        # 保險：5000 埠若仍被本程式殘留占著就一併清掉，確保「關網頁＝背景全部關」
        leftover = _pid_on_port(5000)
        if leftover and leftover != os.getpid() and _pid_is_python(leftover):
            _kill_tree(leftover)
        # 刪登記檔＝標記這一輪是乾淨退出的
        try:
            PID_REGISTRY_FILE.unlink()
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
