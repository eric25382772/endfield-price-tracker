import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 可寫資料目錄：安裝版（Program Files 唯讀）導向 %LOCALAPPDATA%；開發版仍用 BASE_DIR
_INSTALLED = 'Program Files' in BASE_DIR or bool(os.environ.get('ENDFIELD_DATA_DIR'))
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

# Game
GAME_RESET_HOUR = 4  # Daily reset at 4 AM

# OCR
OCR_LANG = 'ch'
OCR_CONFIDENCE_THRESHOLD = 0.6
FUZZY_MATCH_THRESHOLD = 70  # thefuzz uses 0-100 scale

# Trading thresholds
PROFIT_THRESHOLD = 3000      # 利潤 < 3000 建議不買（配額有限）
STOCKPILE_THRESHOLD = 1400   # 自己價格 < 1400 建議囤貨（低於基準30%）

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
