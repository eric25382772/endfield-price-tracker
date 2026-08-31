import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 可寫資料目錄：安裝版導向 %LOCALAPPDATA%；開發版仍用 BASE_DIR
# 偵測方式：Inno Setup 安裝後會在 BASE_DIR 留下 unins000.exe，據此判斷
_INSTALLED = (
    bool(os.environ.get('ENDFIELD_DATA_DIR'))
    or os.path.exists(os.path.join(BASE_DIR, 'unins000.exe'))
    or 'Program Files' in BASE_DIR
)
if _INSTALLED:
    USER_DATA_DIR = os.environ.get('ENDFIELD_DATA_DIR') or \
        os.path.join(os.environ.get('LOCALAPPDATA', BASE_DIR), 'EndfieldTracker')
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    DB_PATH = os.path.join(USER_DATA_DIR, 'prices.db')
    UPLOAD_FOLDER = os.path.join(USER_DATA_DIR, 'uploads')
    FRIEND_REF_DIR = os.path.join(USER_DATA_DIR, 'friend_refs')
else:
    USER_DATA_DIR = BASE_DIR
    DB_PATH = os.path.join(BASE_DIR, 'data', 'prices.db')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    FRIEND_REF_DIR = os.path.join(BASE_DIR, 'data', 'item_images', 'friend')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

# 暫存截圖保留天數：uploads 只增不減會把硬碟吃光（開發機曾累積 1.9 GB）。
# 留幾天是因為查辨識錯誤要靠原始截圖，不要調太短。
UPLOAD_RETENTION_DAYS = 7

# Game
GAME_RESET_HOUR = 4  # Daily reset at 4 AM

# OCR
OCR_LANG = 'ch'
OCR_CONFIDENCE_THRESHOLD = 0.6
FUZZY_MATCH_THRESHOLD = 70  # thefuzz uses 0-100 scale

# Trading thresholds
PROFIT_THRESHOLD = 3000      # 利潤 < 3000 建議不買（配額有限）
# v5.1.5 囤貨合格線：今日買價落在該物品「史上最低~最高」區間的低 N%（0 = 史上最便宜）
STOCKPILE_POS_LIMIT = 15
# v5.1.5 預測容差上限：拿預測值當門檻時給的緩衝，信心越低緩衝越大（信心 1.0 → 0%，信心 0 → 20%）
PRED_TOLERANCE_MAX = 0.20

# v5.1.6 跨日最佳的買進日窗口：今天 ~ D+N。買進日拉越遠，買價越依賴預測、失準越多。
# 115 天回測（2026-05-08~08-30）：N=0 命中 100%／邊際 +1082；N=1 命中 89%／+999；
# N=2 命中 83%／+835；N=3 命中 79%／+737。N=1 出手 45 次，總邊際最高。
CROSS_BUY_WINDOW = 1

# v3.2 等待提示：明日預測利潤需 > 今日 × WAIT_GAIN_RATIO，且信心度 >= WAIT_MIN_CONFIDENCE
WAIT_GAIN_RATIO = 1.2        # 明日預測比今日高 20% 才值得等
WAIT_MIN_CONFIDENCE = 0.5    # 預測信心度門檻

# v4.1 峰值感知賣出：D+1 預測 > 今日實際好友價 × 此值才算「還在漲」，否則視為已達高點 → 可賣
SELL_RISING_MARGIN = 1.03

# v3.2 可買徽章：利潤 >= 同區最高利潤 × BUYABLE_RATIO 才算「次優選擇」
BUYABLE_RATIO = 0.7

# v4.0.1 資料不足警告：預測信心度低於此值（樣本太少）顯示「僅供參考」
DATA_THIN_CONFIDENCE = 0.4

# Regions
REGIONS = {
    'valley_iv': '四號谷地',
    'wuling': '武陵',
}


def get_game_date(dt=None):
    """Get the current game date, accounting for 4 AM daily reset."""
    if dt is None:
        dt = datetime.now()
    if dt.hour < GAME_RESET_HOUR:
        dt -= timedelta(days=1)
    return dt.strftime('%Y-%m-%d')


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
