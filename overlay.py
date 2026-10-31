"""遊戲內小視窗：浮在遊戲畫面上的迷你利潤表。

為什麼不是另開一個網頁：遊戲開無邊框視窗時，瀏覽器沒辦法一直釘在最上層。
這裡用 Python 內建的 tkinter 畫一個永遠置頂的小視窗，不需要多裝任何套件。

資料一律跟 Flask 要（/api/overlay），計算邏輯與 /compare 共用，兩邊建議永遠一致。
整個視窗跑在自己的執行緒，scanner 用下面那幾個 set_* / hide_for_capture 控制它。

大小是跟著內容自己長的，沒有拖拉邊框那套：Tk 的無邊框視窗自己算大小一定會有殘影，
而「看不清楚」用 Ctrl+滾輪改字級就解決了。
"""
import ctypes
import json
import threading
import urllib.request
from pathlib import Path

API = 'http://127.0.0.1:5000/api/overlay'
ICON_PNG = Path(__file__).parent / 'static' / 'images' / 'app64.png'

# 兩段顯示：完整 ↔ 縮成一個圖示（最小化）。按鈕上的字寫的是「按下去會變成什麼」。
MODES = ('full', 'icon')

# 顏色：沿用網頁那套（近黑底 + 暗金 / 玉綠）
BG = '#191919'
SURF = '#1f1f1f'
SURF2 = '#262626'
HOVER = '#3a3a3a'        # 滑過可按項目時的反光
LINE = '#333333'
TXT = '#E6E6E6'
MUT = '#9a9a92'
YELLOW = '#E5C100'
GREEN = '#5FB78A'
UP = '#5BD17C'
DOWN = '#F2655C'
NOTE_BG = '#2a2619'      # 提醒黃字的底，比表格稍亮一點

# 三欄固定寬度（字元數）：欄寬跟著內容跑的話，切檢視或收合時版面會縮一下、數字左右亂跳
COL_NAME, COL_PROFIT, COL_ADVICE = 17, 7, 9

BALL = 64                # 最小化後那顆圖示的邊長（跟 app64.png 一樣大，不縮放才不糊）
BALL_IDLE_ALPHA = 0.75   # 閒置時的不透明度；滑上去變 1.0
TOPMOST_EVERY_MS = 3000  # 每隔多久重新宣告一次置頂，免得被遊戲壓到下面
KEY_COLOR = '#010203'    # 當成「透明」的那個顏色，用來把球的四角挖掉
EDGE = 8                 # 離邊幾個像素內算「壓在邊上」，可以拉縮放
MIN_W, MIN_H = 150, 70
# 只開右邊、下面、右下角。左／上實測一定有殘影：那兩側得「邊改大小邊往左上搬」，
# Windows 會把舊畫面的像素搬去新位置，Tk 這層無法關掉這個行為。要換位置請拖標題列。
CURSORS = {'e': 'size_we', 's': 'size_ns', 'se': 'size_nw_se'}
DEFAULT_FONT = 14        # 預設字級；9／11 級實測都太小
MIN_FONT, MAX_FONT = 7, 40

KIND_COLOR = {
    'best': GREEN, 'good': GREEN, 'stock': YELLOW, 'wait': YELLOW,
    'meh': MUT, 'bad': DOWN, 'none': MUT,
}
REGION_LABEL = {'valley_iv': '四號谷地', 'wuling': '武陵'}
# 地區代表色跟網頁一致（style.css 的 ef-rdot）：谷地暗金、武陵玉綠
REGION_COLOR = {'valley_iv': YELLOW, 'wuling': GREEN}
# 操作說明：每一項都要講清楚「對什麼做什麼」，只寫「移動／調整大小／縮放」看不懂對象
HINT = ('移動視窗：拖曳標題列\n'
        '調整視窗大小：拖曳右／下邊緣\n'
        '縮放文字：Ctrl＋滾輪')

_win = None  # 唯一實例；scanner 只透過模組函式操作
on_note_dismiss = None  # 使用者按掉提醒時通知 scanner，讓網頁那邊的提醒一起關掉


class _Overlay:
    def __init__(self, pos_file):
        import tkinter as tk
        self.tk = tk
        self.pos_file = pos_file
        self.region = 'valley_iv'
        self.view = 'price'
        self.status = None       # 掃描中的提示字，由 scanner 餵
        self.scan_region = None  # 正在掃的是哪一區（還沒判斷出來時是 None）
        self.error = ''
        self.confirm = None      # 要使用者選的問題（例如換區確認），顯示時蓋住整個內容
        self.note = None         # 掃漏提醒那類的黃字，不擋操作
        # 預設收成懸浮球：浮動視窗的慣例是「預設最小化」，不該一開始就佔住畫面。
        # 掃描完成會自動展開（人按 F2 就是要看結果），之後記住使用者自己選的狀態。
        self.mode = 'icon'
        self.stowed = False      # 按過 ✕ 就是 True：掃描不再自動展開（不存檔，下次啟動歸零）
        self._was_scanning = False
        self.data = None         # 最後一次抓到的資料
        self.rows = []           # 列元件的池子，重複使用；多的用 grid_remove 藏起來
        self.shown = 0
        self._drag = (0, 0)
        self._moved = False
        self._ball_pos = None          # 展開前球在哪，收回去要放回同一個位置
        self._moved_since_expand = False
        self._styles = []        # 每個元件各自的字級偏移，換字級時原地改，不重建版面
        self.offset = 0          # 列數放不下時，從第幾項開始顯示
        self._zone = None        # 游標壓在哪條邊上
        self._resizing = None    # 正在從哪條邊拉
        self._rs = None
        self._pending_geo = None
        self._geo_job = None
        self._row_h = {}         # 各字級下一列多高，量過就記著

        cfg = self._load_settings()
        self.base = cfg.get('font', DEFAULT_FONT)
        if cfg.get('mode') in MODES:
            self.mode = cfg['mode']
        self.win_w, self.win_h = cfg.get('w') or None, cfg.get('h') or None

        self.root = tk.Tk()
        self.root.overrideredirect(True)      # 不要標題列，自己畫
        self.root.attributes('-topmost', True)
        self.root.configure(bg=LINE)
        geo = f"+{cfg.get('x', 40)}+{cfg.get('y', 40)}"
        if self.win_w and self.win_h:
            geo = f'{int(self.win_w)}x{int(self.win_h)}' + geo
        self.root.geometry(geo)
        self.root.bind_all('<MouseWheel>', self._on_wheel)
        self.root.bind_all('<Motion>', self._on_motion)
        self.root.bind_all('<Button-1>', self._maybe_resize_start, add='+')
        self.root.bind_all('<B1-Motion>', self._resize_move, add='+')
        self.root.bind_all('<ButtonRelease-1>', self._resize_end, add='+')

        self._build()
        self._apply_mode()
        self._keep_on_screen()   # 上次關機前的位置可能已經在畫面外（換螢幕、改解析度）
        self._keep_topmost()
        self.refresh()

    def _keep_topmost(self):
        """定時重新宣告一次置頂。

        同時有多個置頂視窗時，是「最後被提到前面的那個」在最上層 ——
        遊戲切換畫面或重新取得焦點時有機會把小視窗壓下去。
        重新宣告用的是不搶焦點的方式，不會打斷遊戲操作。"""
        try:
            self.root.attributes('-topmost', True)
        except Exception:
            pass
        self.root.after(TOPMOST_EVERY_MS, self._keep_topmost)

    # ---------- 字級 ----------
    def _font(self, delta=0, bold=False, mono=False):
        family = 'Consolas' if mono else 'Microsoft JhengHei'
        return (family, max(6, self.base + delta)) + (('bold',) if bold else ())

    @property
    def _wrap(self):
        return 30 * self.base   # 折行寬度也要跟著字級走，不然大字會爆版

    def _styled(self, widget, delta=0, bold=False, mono=False, wrap=0):
        """套字級並記下來。換字級時逐一原地改，不重建版面。"""
        opts = {'font': self._font(delta, bold, mono)}
        if wrap:
            opts['wraplength'] = max(80, self._wrap - wrap)
        widget.configure(**opts)
        self._styles.append((widget, delta, bold, mono, wrap))
        return widget

    def _clickable(self, w, cmd, base_bg, tip=''):
        """可以按的東西：游標變手指、滑過去會亮一下（跟網頁的 hover 一樣）。"""
        w.configure(cursor='hand2')
        w.bind('<Button-1>', lambda e: cmd())
        w.bind('<Enter>', lambda e: w.configure(bg=HOVER))
        w.bind('<Leave>', lambda e: w.configure(bg=base_bg))
        if tip:
            self._tip(w, tip)
        return w

    def _tip(self, widget, text):
        """滑上去等一下會冒出來的小說明。沒有這個，使用者不會知道哪裡能點。"""
        state = {'win': None, 'job': None}

        def show():
            state['job'] = None
            try:
                tw = self.tk.Toplevel(self.root)
                tw.overrideredirect(True)
                tw.attributes('-topmost', True)
                self._styled(self.tk.Label(tw, text=text, bg=SURF2, fg=TXT,
                                           padx=7, pady=3), -1).pack()
                tw.geometry(f'+{widget.winfo_rootx()}+'
                            f'{widget.winfo_rooty() + widget.winfo_height() + 4}')
                state['win'] = tw
            except Exception:
                pass

        def enter(_):
            state['job'] = widget.after(500, show)

        def leave(_):
            if state['job'] is not None:
                widget.after_cancel(state['job'])
                state['job'] = None
            if state['win'] is not None:
                state['win'].destroy()
                state['win'] = None

        widget.bind('<Enter>', enter, add='+')
        widget.bind('<Leave>', leave, add='+')
        widget.bind('<Button-1>', leave, add='+')

    def set_font(self, base):
        """換字級：每個元件原地換，不重建版面。"""
        base = max(MIN_FONT, min(MAX_FONT, base))
        if base == self.base:
            return
        self.base = base
        alive = []
        for w, delta, bold, mono, wrap in self._styles:
            try:
                if not w.winfo_exists():
                    continue
                opts = {'font': self._font(delta, bold, mono)}
                if wrap:
                    opts['wraplength'] = max(80, self._wrap - wrap)
                w.configure(**opts)
                alive.append((w, delta, bold, mono, wrap))
            except Exception:
                pass
        self._styles = alive
        self._row_h.clear()                 # 字級變了，列高要重量
        self._rewrap_note()
        self.root.minsize(self._table_width() + 2, 1)
        self._save_settings()

    # ---------- 版面 ----------
    def _build(self):
        tk = self.tk
        self.outer = tk.Frame(self.root, bg=LINE, padx=1, pady=1)
        self.outer.pack(fill='both', expand=True)

        # 標題列：地區切換 + 收成球。整條可以拖著搬家（只有這條）
        bar = self.bar = tk.Frame(self.outer, bg=BG)
        bar.pack(fill='x')
        self.region_btns = {}
        for rid, label in REGION_LABEL.items():
            b = self._styled(tk.Label(bar, text=label, bg=BG, fg=MUT, padx=8, pady=3))
            b.pack(side='left')
            self._clickable(b, lambda r=rid: self.set_region(r), BG)
            self.region_btns[rid] = b
        close = self._styled(tk.Label(bar, text='✕', bg=BG, fg=MUT, padx=8, pady=3))
        close.pack(side='right')
        self._clickable(close, self.stow, BG, tip='收成懸浮球；點那顆球才會再展開')
        self._make_draggable(bar)

        # 檢視切換 + 剩餘配額
        head = self.head = tk.Frame(self.outer, bg=SURF)
        head.pack(fill='x')
        self.view_btns = {}
        for vid, label in (('price', '當日價格'), ('stock', '囤貨')):
            b = self._styled(tk.Label(head, text=label, bg=SURF, fg=MUT, padx=7, pady=2), -1)
            b.pack(side='left')
            self._clickable(b, lambda v=vid: self.set_view(v), SURF)
            self.view_btns[vid] = b
        self.quota_lbl = self._styled(tk.Label(head, text='', bg=SURF, fg=MUT, padx=8), -1)
        self.quota_lbl.pack(side='right')

        self.body = tk.Frame(self.outer, bg=SURF)
        self.body.pack(fill='both', expand=True)

        # 表格只建一次。之後換內容只換文字、改顯示幾列，不拆掉重建（拆了會閃）
        self.table = tk.Frame(self.body, bg=SURF)
        self.table.columnconfigure(0, weight=1)
        heads = (('貨物', 'w', COL_NAME), ('利潤', 'e', COL_PROFIT), ('建議', 'e', COL_ADVICE))
        for col, (text, anchor, width) in enumerate(heads):
            self._styled(tk.Label(self.table, text=text, bg=SURF2, fg=MUT, anchor=anchor,
                                  width=width, padx=6, pady=1),
                         -2).grid(row=0, column=col, sticky='ew')
        # 放不下時右邊那條捲軸（跟網頁一樣）；放得下就收起來
        self.sb = tk.Canvas(self.table, width=9, bg=SURF2, highlightthickness=0, bd=0)
        self.sb.bind('<Button-1>', self._sb_drag)
        self.sb.bind('<B1-Motion>', self._sb_drag)
        self._sb_span = (0, 0)
        self.msg_frame = None
        self.note_frame = None
        self.note_lbl = None
        self.confirm_frame = None

        # 底下那條：狀態訊息。純顯示，不能拖（拖曳只在標題列）。
        # height 固定成兩行：它的高度會被拿去算「放得下幾列」，一旦隨文字長短變高變矮，
        # 切個地區回來列數就跟著跳、底下空一塊。
        self.foot = self._styled(
            tk.Label(self.outer, text='', bg=BG, fg=MUT, anchor='w', justify='left',
                     height=2, padx=8, pady=3), -1, wrap=1)
        self.foot.pack(fill='x')

        # 最小化：只剩追蹤器那顆圖示浮在畫面上（Messenger 懸浮球那種用法），點一下展開。
        # 圖本身就是去背的，所以不要在底下畫任何形狀 —— 畫了就等於把去背蓋掉。
        # 底色用透明色，四周才不會出現方框。
        self.icon_lbl = tk.Canvas(self.outer, width=BALL, height=BALL, bg=KEY_COLOR,
                                  highlightthickness=0, bd=0)
        # 滑上去才畫的外圈：閒置時看不到，滑過去才知道這東西可以點
        self._ball_ring = self.icon_lbl.create_oval(1, 1, BALL - 2, BALL - 2,
                                                    outline=YELLOW, width=2, state='hidden')
        img = self._icon_img()
        if img is not None:
            self.icon_lbl.create_image(BALL // 2, BALL // 2, image=img)
        else:
            self.icon_lbl.create_text(BALL // 2, BALL // 2, text='EF', fill=YELLOW,
                                      font=('Microsoft JhengHei', 12, 'bold'))
        # 先掛搬移，再用 add='+' 疊上「點一下回全開」：同一事件綁兩次會覆蓋，
        # 順序錯的話點圖示只會搬家、回不去
        self._make_draggable(self.icon_lbl)
        self.icon_lbl.bind('<ButtonRelease-1>', self._icon_click, add='+')
        self.icon_lbl.configure(cursor='hand2')
        # 閒置半透明、滑上去變清楚並浮出外圈 —— 懸浮球都是這樣讓人看出它能互動的
        self.icon_lbl.bind('<Enter>', lambda e: self._ball_hover(True), add='+')
        self.icon_lbl.bind('<Leave>', lambda e: self._ball_hover(False), add='+')
        self._tip(self.icon_lbl, '點一下展開 · 可拖曳移動')

    def _icon_img(self):
        """追蹤器那顆圖示。Tk 只吃 PNG，用專案裡轉好的那張。

        master 一定要指定：不指定的話 tkinter 會去找「預設的那個 Tk」，
        而那個很可能是啟動提示視窗留下的殘影，於是圖載不進來、只剩備用的文字。"""
        if not hasattr(self, '_icon_cache'):
            self._icon_cache = None
            try:
                self._icon_cache = self.tk.PhotoImage(master=self.root, file=str(ICON_PNG))
            except Exception as e:
                print(f"  [小視窗圖示載入失敗] {e}")
        return self._icon_cache

    # ---------- 搬家（只有標題列） ----------
    def _make_draggable(self, widget):
        widget.bind('<Button-1>', self._drag_start)
        widget.bind('<B1-Motion>', self._drag_move)
        widget.bind('<ButtonRelease-1>', self._drag_end)

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self._moved = False

    def _drag_move(self, e):
        self._moved = True
        self._moved_since_expand = True
        self.root.geometry(f'+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}')

    def _drag_end(self, e):
        self._keep_on_screen()
        self._save_settings()   # 放開才存，拖的過程不寫檔

    def _screen_rect(self):
        """整個桌面的範圍（含第二台螢幕）。拿不到就退回主螢幕。"""
        try:
            m = ctypes.windll.user32.GetSystemMetrics
            x, y, w, h = m(76), m(77), m(78), m(79)   # SM_*VIRTUALSCREEN
            if w > 0 and h > 0:
                return x, y, w, h
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _keep_on_screen(self):
        """把視窗拉回畫面內。

        展開時視窗會往右往下長，原本貼著螢幕邊的話，標題列會整條被推到畫面外 ——
        那就再也拖不回來了。"""
        self.root.update_idletasks()
        sx, sy, sw, sh = self._screen_rect()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        nx = min(max(sx, x), max(sx, sx + sw - w))
        ny = min(max(sy, y), max(sy, sy + sh - h))
        if (nx, ny) != (x, y):
            self.root.geometry(f'+{int(nx)}+{int(ny)}')

    def _icon_click(self, e):
        """圖示上『點一下』才是展開；拖著走不算。"""
        if not self._moved:
            self.stowed = False   # 他自己點開了，掃描自動展開就恢復
            self.set_mode('full')

    def _ball_hover(self, on):
        if self.mode != 'icon':
            return
        self.icon_lbl.itemconfigure(self._ball_ring, state=('normal' if on else 'hidden'))
        try:
            self.root.attributes('-alpha', 1.0 if on else BALL_IDLE_ALPHA)
        except Exception:
            pass

    def _on_wheel(self, e):
        """滾輪上下滑；按著 Ctrl 滾＝改字級（跟瀏覽器、檔案總管同一套）。

        Windows 預設「滑鼠停在哪個視窗就滾哪個」，所以遊戲在前景也動得了。"""
        if e.state & 0x4:
            self.set_font(self.base + (1 if e.delta > 0 else -1))
            return
        self._scroll(-1 if e.delta > 0 else 1)

    # ---------- 自訂大小（右邊／下面／右下角） ----------
    def _zone_at(self, xr, yr):
        """游標壓在哪一條邊上。回傳 n/s/e/w 的組合，不在邊上就 None。"""
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if not (x <= xr <= x + w and y <= yr <= y + h):
            return None
        z = ''
        if (y + h) - yr <= EDGE:
            z += 's'
        if (x + w) - xr <= EDGE:
            z += 'e'
        return z or None

    def _on_motion(self, e):
        """移到邊緣 → 換成縮放游標，讓人知道這裡拉得動。"""
        if self._resizing:
            return
        z = self._zone_at(e.x_root, e.y_root)
        if z != self._zone:
            self._zone = z
            try:
                self.root.configure(cursor=CURSORS.get(z, ''))
            except Exception:
                pass

    def _maybe_resize_start(self, e):
        """壓在邊上才算縮放。按鈕上的點擊絕對不能被搶走。"""
        try:
            if str(e.widget.cget('cursor')) == 'hand2':
                return
        except Exception:
            pass
        self._resizing = self._zone_at(e.x_root, e.y_root)

    def _resize_move(self, e):
        """大小 = 指標絕對位置 − 視窗左上角（Tk 官方做法），不是把位移量加總。

        只改大小、絕不改位置：一旦邊改大小邊搬家，Windows 會把舊畫面的像素搬去
        新位置，那些沒被蓋掉的就是殘影，Tk 這層關不掉。"""
        if not self._resizing:
            return
        z = self._resizing
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if 'e' in z:
            w = max(MIN_W, self.root.winfo_pointerx() - self.root.winfo_rootx())
        if 's' in z:
            h = max(MIN_H, self.root.winfo_pointery() - self.root.winfo_rooty())
        self._pending_geo = (int(w), int(h))
        if self._geo_job is None:
            self._geo_job = self.root.after(16, self._apply_geo)   # 併成 60fps

    def _apply_geo(self):
        self._geo_job = None
        geo, self._pending_geo = self._pending_geo, None
        if not geo:
            return
        self.win_w, self.win_h = geo
        self.root.geometry(f'{geo[0]}x{geo[1]}')
        self._rewrap_note()
        if self._rows_that_fit() != self.shown:   # 放得下的列數變了才重畫
            self._paint()

    def _rewrap_note(self):
        """視窗寬度或字級變了就重算提醒的折行寬度。整個重畫太重，只改這一個屬性。"""
        if self.note_lbl is None:
            return
        try:
            self.note_lbl.configure(wraplength=self._note_wrap())
        except Exception:
            pass

    def _resize_end(self, e):
        if not self._resizing:
            return
        self._resizing = None
        if self._geo_job is not None:
            self.root.after_cancel(self._geo_job)
            self._geo_job = None
        self._apply_geo()
        self._paint()
        self._save_settings()

    def _row_height(self):
        """一列實際多高。畫面上已經有列就直接量那一列，最準。"""
        if self.rows:
            try:
                h = self.rows[0]['name'].winfo_reqheight()
                if h > 1:
                    self._row_h[self.base] = h
                    return h
            except Exception:
                pass
        h = self._row_h.get(self.base)
        if not h:
            tk = self.tk
            probe = tk.Frame(self.body, bg=SURF)
            probe.pack()
            lbl = self._styled(tk.Label(probe, text='測', bg=SURF, pady=1))
            lbl.pack()
            self.body.update_idletasks()
            h = self._row_h[self.base] = max(1, lbl.winfo_reqheight())
            probe.destroy()
        return h

    def _rows_that_fit(self):
        """自己拉過高度時，一頁放得下幾列；沒拉過就回 None（有幾項列幾項）。

        各段高度一律用量的，不要用猜的 —— 猜多了就會像之前那樣，
        明明還有空間卻少顯示一兩列，底下留一大塊空白。"""
        if not self.win_h or self.mode != 'full':
            return None
        self.root.update_idletasks()
        row = self._row_height()
        head_row = row
        try:
            bbox = self.table.grid_bbox(0, 0)      # 表頭那一格
            if bbox and bbox[3] > 1:
                head_row = bbox[3]
        except Exception:
            pass
        chrome = (self.bar.winfo_reqheight() + self.head.winfo_reqheight()
                  + self.foot.winfo_reqheight() + head_row + 2)   # +2＝外框那一圈
        if self.note_frame is not None:
            chrome += self.note_frame.winfo_reqheight()
        return max(1, int((self.win_h - chrome) // row))

    def _scroll(self, step):
        """只換每一列的文字，不重建版面 —— 重建會整個閃一下。"""
        items = self._items()
        n = self.shown
        if not n or len(items) <= n:
            return
        offset = max(0, min(self.offset + step, len(items) - n))
        if offset == self.offset:
            return
        self.offset = offset
        for w, it in zip(self.rows, items[offset:offset + n]):
            self._fill_row(w, it)
        self._draw_thumb()

    # ---------- 三段顯示 ----------
    def stow(self):
        """✕：收成懸浮球，而且掃描也不准把它打開，直到使用者自己點那顆球。"""
        self.stowed = True
        self.set_mode('icon')

    def set_mode(self, mode, persist=True):
        # 球在螢幕右邊時，展開會被「拉回畫面內」往左推。收回去要放回原位，
        # 不然每展開一次球就往左跑一截。但展開後自己搬過家就以搬到的位置為準。
        if self.mode == 'icon' and mode != 'icon':
            self._ball_pos = (self.root.winfo_x(), self.root.winfo_y())
            self._moved_since_expand = False
        self.mode = mode
        if persist:
            self._save_settings()
        self._apply_mode()
        if mode == 'icon' and self._ball_pos and not self._moved_since_expand:
            self.root.geometry(f'+{self._ball_pos[0]}+{self._ball_pos[1]}')
            self._keep_on_screen()
        self._paint()

    def _apply_mode(self):
        """最小化時把標題列、表格、底下那條全收起來，只留圖示。"""
        for w in (self.bar, self.head, self.body, self.foot, self.icon_lbl):
            w.pack_forget()
        if self.mode == 'icon':
            self.root.minsize(1, 1)
            # 視窗、外框那一層都要換成透明色，只漏掉一層就會看到一圈方框
            self.root.configure(bg=KEY_COLOR)
            self.outer.configure(bg=KEY_COLOR, padx=0, pady=0)
            try:
                self.root.attributes('-alpha', BALL_IDLE_ALPHA)   # 閒置時淡一點，不擋畫面
            except Exception:
                pass
            try:
                self.root.attributes('-transparentcolor', KEY_COLOR)   # 四角透明＝看起來是圓的
            except Exception:
                pass
            self.root.wm_geometry('')      # 縮成球就只有球那麼大
            self.icon_lbl.pack()
            return
        try:
            self.root.attributes('-transparentcolor', '')
            self.root.attributes('-alpha', 1.0)
        except Exception:
            pass
        self.root.configure(bg=LINE)
        self.outer.configure(bg=LINE, padx=1, pady=1)
        self.bar.pack(fill='x')
        self.head.pack(fill='x')
        self.foot.pack(side='bottom', fill='x')
        self.body.pack(fill='both', expand=True)
        self.offset = 0
        # 視窗永遠不會比表格窄：顯示訊息（表格收起來）時才不會縮成另一個寬度
        self.root.minsize(self._table_width() + 2, 1)
        if self.win_w and self.win_h:
            self.root.wm_geometry(f'{int(self.win_w)}x{int(self.win_h)}')
        else:
            self.root.wm_geometry('')      # 沒拉過就跟著內容長
        self._keep_on_screen()

    # ---------- 位置 / 字級記憶 ----------
    def _load_settings(self):
        try:
            return json.loads(self.pos_file.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _save_settings(self):
        try:
            self.pos_file.write_text(json.dumps({
                'x': self.root.winfo_x(), 'y': self.root.winfo_y(),
                'font': self.base, 'mode': self.mode,
                'w': self.win_w, 'h': self.win_h,
            }), encoding='utf-8')
        except Exception:
            pass

    # ---------- 內容 ----------
    def _clear_temp(self):
        """清掉臨時區塊（訊息／提醒／問題）。表格是常駐的，不能清。"""
        for attr in ('msg_frame', 'note_frame', 'confirm_frame'):
            w = getattr(self, attr, None)
            if w is not None:
                w.destroy()
                setattr(self, attr, None)
        self.note_lbl = None     # 跟著 note_frame 一起沒了

    def _hide_content(self):
        self._clear_temp()
        self.table.pack_forget()

    def _table_width(self):
        """表格的自然寬度。訊息一律折到這個寬度，視窗寬度才不會跟著文字長短變來變去。"""
        self.root.update_idletasks()
        return max(160, self.table.winfo_reqwidth())

    def _msg(self, big, small=''):
        tk = self.tk
        wrap = self._table_width() - 36
        box = self.msg_frame = tk.Frame(self.body, bg=SURF, padx=18, pady=16)
        box.pack(fill='x')
        lbl = tk.Label(box, text=big, bg=SURF, fg=TXT, wraplength=wrap)
        self._styled(lbl, 1).pack()
        if small:
            lbl2 = tk.Label(box, text=small, bg=SURF, fg=MUT, justify='center',
                            wraplength=wrap)
            self._styled(lbl2, -1).pack(pady=(4, 0))

    def _show_rows(self, n):
        """讓表格顯示 n 列。列是共用的：不夠就補、多的藏起來，從頭到尾不拆元件。"""
        tk = self.tk
        while len(self.rows) < n:
            i = len(self.rows)
            name = self._styled(tk.Label(self.table, bg=SURF, fg=TXT, anchor='w',
                                         width=COL_NAME, padx=6, pady=1))
            profit = self._styled(tk.Label(self.table, bg=SURF, anchor='e',
                                           width=COL_PROFIT, padx=6), 1, bold=True, mono=True)
            advice = self._styled(tk.Label(self.table, bg=SURF, anchor='e',
                                           width=COL_ADVICE, padx=6), -1)
            name.grid(row=i + 1, column=0, sticky='ew')
            profit.grid(row=i + 1, column=1, sticky='e')
            advice.grid(row=i + 1, column=2, sticky='e')
            self.rows.append({'name': name, 'profit': profit, 'advice': advice})

        for i, w in enumerate(self.rows):
            for cell in w.values():
                cell.grid() if i < n else cell.grid_remove()
        self.shown = n

    def _show_scrollbar(self, total, n):
        self._sb_span = (total, n)
        if total > n:
            self.sb.grid(row=1, column=3, rowspan=max(1, n), sticky='ns')
            self.body.update_idletasks()
            self._draw_thumb()
        else:
            self.sb.grid_remove()

    def _draw_thumb(self):
        """捲軸上那塊可以拖的條。"""
        total, n = self._sb_span
        if total <= n:
            return
        h = max(1, self.sb.winfo_height())
        th = max(16, int(h * n / total))
        room, maxoff = h - th, total - n
        y = int(self.offset / maxoff * room) if maxoff > 0 else 0
        self.sb.delete('all')
        self.sb.create_rectangle(2, y, 8, y + th, fill=MUT, outline='')

    def _sb_drag(self, e):
        total, n = self._sb_span
        if total <= n:
            return
        h = max(1, self.sb.winfo_height())
        want = int(round(e.y / h * total)) - n // 2
        self._scroll(want - self.offset)

    def _fill_row(self, w, it):
        p = it['profit']
        if p is None:
            txt, color = '—', MUT
        else:
            txt = f'+{p}' if p > 0 else str(p)
            color = UP if p > 0 else (DOWN if p < 0 else MUT)
        w['name'].configure(text=it['name'])
        w['profit'].configure(text=txt, fg=color)
        w['advice'].configure(text=it['advice'], fg=KIND_COLOR.get(it['kind'], MUT))

    def _items(self):
        return (self.data or {}).get('items') or []

    def _scanning_here(self):
        """正在掃的是不是「現在這一區」。掃谷地時切去看武陵，武陵要照常顯示資料。
        scan_region 是 None＝還沒判斷出地區，這時也算，免得資料顯示到錯的一區。"""
        return bool(self.status) and self.scan_region in (None, self.region)

    def _note_wrap(self):
        """提醒文字的折行寬度。要跟著視窗實際寬度走 —— 用固定值的話，
        視窗拉寬後字還是折在原處（「還有 6」就被丟到上一行），拉窄後又會蓋掉 ✕。"""
        return max(80, int(self.win_w or self._table_width()) - 46)

    def _draw_note(self):
        """掃漏提醒那類的黃字。不擋操作，按 ✕ 收掉，下次掃描又有漏才會再出現。"""
        tk = self.tk
        bar = self.note_frame = tk.Frame(self.body, bg=NOTE_BG)
        bar.pack(fill='x', before=self.table)
        # ✕ 要先 pack：Tk 是先排先得，後排的才會被擠掉，關閉鈕不能是被犧牲的那個
        x = self._styled(tk.Label(bar, text='✕', bg=NOTE_BG, fg=YELLOW, padx=7), -1)
        x.pack(side='right')
        self.note_lbl = self._styled(
            tk.Label(bar, text=self.note, bg=NOTE_BG, fg=YELLOW, anchor='w',
                     justify='left', padx=8, pady=5, wraplength=self._note_wrap()), -1)
        self.note_lbl.pack(side='left', fill='x', expand=True)
        self._clickable(x, self._clear_note, NOTE_BG)

    def _clear_note(self):
        self.note = None
        self._paint()
        # 提醒是同一件事的兩個顯示處，關掉一邊另一邊也要跟著關。寫檔另開執行緒，不卡住 Tk。
        if on_note_dismiss:
            threading.Thread(target=on_note_dismiss, daemon=True).start()

    def _draw_confirm(self):
        """要使用者二選一的問題。不做成這樣的話，人在遊戲裡就得切出去點網頁。"""
        tk, c = self.tk, self.confirm
        box = self.confirm_frame = tk.Frame(self.body, bg=SURF, padx=12, pady=11)
        box.pack(fill='x')
        self._styled(tk.Label(box, text=c['title'], bg=SURF, fg=YELLOW, anchor='w'),
                     bold=True).pack(fill='x')
        self._styled(tk.Label(box, text=c['text'], bg=SURF, fg=TXT, anchor='w',
                              justify='left'), -1, wrap=20).pack(fill='x', pady=(5, 0))
        btns = tk.Frame(box, bg=SURF)
        btns.pack(fill='x', pady=(10, 0))
        yes = self._styled(tk.Label(btns, text=c['yes_label'], bg=DOWN, fg='#111',
                                    padx=10, pady=4), bold=True)
        yes.pack(side='right')
        self._clickable(yes, lambda: self._answer('yes'), DOWN)
        no = self._styled(tk.Label(btns, text=c['no_label'], bg=SURF2, fg=TXT,
                                   padx=10, pady=4))
        no.pack(side='right', padx=(0, 8))
        self._clickable(no, lambda: self._answer('no'), SURF2)

    def _answer(self, which):
        c, self.confirm = self.confirm, None
        self.refresh()
        fn = c.get(which)
        if fn:
            threading.Thread(target=fn, daemon=True).start()

    # ---------- 取資料 / 重畫 ----------
    def refresh(self):
        """重畫。只在掃描完成或使用者切換時呼叫，不做每秒輪詢。

        抓資料一定要另開執行緒：伺服器要算一輪才回，卡在 Tk 這條的話，
        截圖前「把小視窗藏起來」就得排在它後面，快門會被拖慢一秒以上，
        連按熱鍵時就會拍到使用者已經切走的畫面（v7.0.1 踩過）。"""
        for rid, b in self.region_btns.items():
            b.configure(fg=(REGION_COLOR[rid] if rid == self.region else MUT))
        for vid, b in self.view_btns.items():
            b.configure(fg=(TXT if vid == self.view else MUT))

        # 要你回答的問題最優先，蓋住其他所有內容
        if self.confirm:
            self._hide_content()
            self._draw_confirm()
            self.quota_lbl.configure(text='')
            self.foot.configure(text='選一個才會繼續', fg=YELLOW)
            return

        want = (self.region, self.view)
        threading.Thread(target=self._fetch, args=(want,), daemon=True).start()

    def _fetch(self, want):
        region, view = want
        data = None
        try:
            with urllib.request.urlopen(f'{API}?region={region}&view={view}', timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception:
            pass
        try:
            self.root.after(0, lambda: self._render(data, want))
        except Exception:
            pass

    def _render(self, data, want):
        if want != (self.region, self.view) or self.confirm:
            return      # 抓的過程中使用者又切走了 → 這份是舊的，丟掉
        self.data = data
        self._paint()

    def _paint(self):
        """重畫內容。表格本身不拆，只換文字與顯示列數，所以不會閃。"""
        data = self.data
        self._clear_temp()

        if self.mode == 'icon':
            self.table.pack_forget()
            return

        if data is None:
            self.table.pack_forget()
            # 掃描中要資料偶爾會逾時（OCR 正忙），別把它講成追蹤器掛了
            if self._scanning_here():
                self._msg('辨識中…', self.status)
            else:
                self._msg('連不上追蹤器', '請確認追蹤器還開著')
            return

        if self._scanning_here():
            # 掃描中：那格改成進度提示（網頁是在地區標題旁放轉圈圈，同一個意思）
            self.quota_lbl.configure(text=f'{self.status}…', fg=YELLOW)
        else:
            # 跟網頁一致（compare.html 的 data-quota）：剩餘配額是「今天還能買多少」，
            # 只跟當日價格有關；囤貨看的是已經買到手的，所以那頁不顯示。沒掃到也不顯示。
            q, m = data.get('remaining'), data.get('max_quota')
            show_quota = self.view == 'price' and q is not None and m
            # 配額頂到上限時網頁會轉紅（今天不買那些額度就浪費了），這裡也跟著轉
            self.quota_lbl.configure(
                text=(f'剩餘 {q} / {m}' if show_quota else ''),
                fg=(DOWN if show_quota and q >= m else MUT))

        items = data.get('items') or []
        if not items and self._scanning_here():
            self.table.pack_forget()
            # 還沒掃到任何一筆，這時才整頁顯示辨識中；掃到之後就換成表格邊掃邊填
            self._msg('辨識中…', self.status)
        elif not items:
            self.table.pack_forget()
            # 指引文字跟網頁的空白表格一致（compare.html 的導引區）；
            # 操作說明只在完整模式附上 —— 精簡模式本來就是要小，不該被說明撐大
            tail = ('\n\n' + HINT) if self.mode == 'full' else ''
            if self.view == 'stock':
                self._msg(f'手上沒有{REGION_LABEL[self.region]}的囤貨',
                          '物資調度 → 彈性需求物資的\n「目前持有」畫面按 F4' + tail)
            else:
                self._msg(f'今天還沒掃過{REGION_LABEL[self.region]}',
                          '物資調度 → 彈性需求物資的「市場」畫面按 F2\n'
                          '再點各商品 → 查看好友價格，每項按一次 F3' + tail)
        else:
            self.table.pack(fill='both', expand=True)
            if self.note:
                self._draw_note()
            # 自己拉小就只放得下幾列，其餘用滾輪／捲軸看
            n = max(1, min(self._rows_that_fit() or len(items), len(items)))
            self.offset = max(0, min(self.offset, len(items) - n))
            self._show_rows(n)
            for w, it in zip(self.rows, items[self.offset:self.offset + n]):
                self._fill_row(w, it)
            self._show_scrollbar(len(items), n)

        if self.status and self.scan_region:
            self.foot.configure(text=f'{REGION_LABEL[self.scan_region]}辨識中…', fg=YELLOW)
        elif self.error:
            self.foot.configure(text=self.error, fg=DOWN)
        elif items and all(i['profit'] is None for i in items):
            self.foot.configure(text='還沒掃好友價，算不出利潤', fg=YELLOW)
        elif len(items) > self.shown:
            self.foot.configure(text='滾輪可查看其餘項目', fg=MUT)
        else:
            self.foot.configure(text='', fg=MUT)

        # 內容多寡會改變視窗大小，貼著螢幕邊時可能被推出畫面
        self._keep_on_screen()

    # ---------- 對外 ----------
    def set_region(self, region):
        if region in REGION_LABEL and region != self.region:
            self.region = region
            self.refresh()

    def set_view(self, view):
        if view in ('price', 'stock') and view != self.view:
            self.view = view
            self.refresh()

    def show(self):
        self.root.deiconify()
        self.root.attributes('-topmost', True)



# ===== 下面是 scanner 唯一會用到的介面 =====

def start(pos_file):
    """在自己的執行緒開一個小視窗。重複呼叫只會有一個。"""
    global _win
    if _win is not None:
        return

    ready = threading.Event()

    def run():
        global _win
        try:
            _win = _Overlay(pos_file)
        except Exception as e:
            print(f"  [小視窗啟動失敗] {e}")
            ready.set()
            return
        ready.set()
        _win.root.mainloop()

    threading.Thread(target=run, daemon=True).start()
    ready.wait(timeout=10)


def _call(fn):
    """Tk 不能跨執行緒直接碰，所有操作都丟回它自己的迴圈執行。"""
    if _win is None:
        return
    try:
        _win.root.after(0, fn)
    except Exception:
        pass


def set_scan_state(region=None, view=None, status=None, error=''):
    """掃描狀態變化時由 scanner 呼叫：跟著切地區／檢視，並重畫。"""
    def apply():
        if region:
            _win.region = region
        if view:
            _win.view = view
        _win.status = status
        _win.scan_region = region if status else None
        _win.error = error or ''
        if status:
            _win.note = None   # 又開始掃了，上一輪的缺漏清單先收掉，掃完會再算一次
            _win._was_scanning = True
            if _win.mode == 'icon' and not _win.stowed:
                # 掃描一開始就展開，讓人看得到進度與結果。不存檔：這是程式自己開的，
                # 不是使用者的選擇，下次啟動還是要回到他自己設定的那個狀態。
                _win.set_mode('full', persist=False)
        elif _win._was_scanning:
            _win._was_scanning = False
        _win.refresh()
    _call(apply)


def set_note(text):
    """掃漏提醒那類的黃字；text=None 收掉。"""
    def apply():
        _win.note = text or None
        _win.refresh()
    _call(apply)


def ask(title=None, text='', on_yes=None, on_no=None, yes_label='確定', no_label='取消'):
    """在小視窗上問一個二選一的問題；title=None 代表把問題收掉。

    問題一出現就把視窗叫回來：人就算把它關掉了，也得看得到這個才知道卡在哪。"""
    def apply():
        _win.confirm = ({'title': title, 'text': text, 'yes': on_yes, 'no': on_no,
                         'yes_label': yes_label, 'no_label': no_label} if title else None)
        if title:
            _win.show()
        _win.refresh()
    _call(apply)


def set_pages_open(is_open):
    """網頁全關就跟著收起來，網頁再開就回來。

    不動 mode／stowed：那是使用者自己選的展開狀態，網頁開關不該把它洗掉。"""
    def apply():
        if is_open:
            _win.show()
        else:
            _win.root.withdraw()
    _call(apply)


def hide_for_capture(rect=None):
    """截圖前把自己藏起來，回傳「剛剛是不是顯示中」。

    小視窗浮在遊戲上面，不藏起來會被拍進截圖，OCR 就讀到自己畫的字了。
    但快門必須快：使用者會連按熱鍵然後馬上切下一個畫面，這裡每多等一下，
    就多一分拍到「他已經切走的畫面」的機會（v7.0.1 踩過，好友價掃描失敗率飆到 58%）。
    所以沒疊到截圖範圍就完全不動，等待也設上限。"""
    if _win is None:
        return False
    if rect and not _overlaps(rect):
        return False

    done = threading.Event()

    def apply():
        try:
            _win.root.withdraw()
        finally:
            done.set()

    _call(apply)
    done.wait(timeout=0.3)
    return True


def _overlaps(rect):
    """小視窗跟這次要截的範圍有沒有疊到。問不出來就當有疊，寧可慢也不要拍到自己。"""
    try:
        w = _win.root
        x, y = w.winfo_x(), w.winfo_y()
        x2, y2 = x + w.winfo_width(), y + w.winfo_height()
        return not (x2 <= rect['left'] or x >= rect['left'] + rect['width']
                    or y2 <= rect['top'] or y >= rect['top'] + rect['height'])
    except Exception:
        return True


def restore_after_capture(was_visible):
    if was_visible:
        _call(lambda: _win.show())


def stop():
    """收工時從 Tk 自己的執行緒收掉視窗，並等它真的消失才回去。

    直接讓行程結束會由別的執行緒去清 Tcl，那會 abort 整個行程（splash 當年踩過同一個坑）；
    不等它關完就往下走，則會看到「網頁都關了小視窗還浮在那」。"""
    global _win
    if _win is None:
        return
    w, _win = _win, None
    done = threading.Event()

    def apply():
        try:
            w.root.withdraw()   # 先消失，destroy 慢一點沒關係
            w.root.destroy()
        finally:
            done.set()

    try:
        w.root.after(0, apply)
        done.wait(timeout=2)
    except Exception:
        pass
