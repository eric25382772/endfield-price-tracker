import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database
DB_PATH = os.path.join(BASE_DIR, 'data', 'prices.db')

# Upload
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

# Game
GAME_RESET_HOUR = 4  # Daily reset at 4 AM

# OCR
OCR_LANG = 'ch'
OCR_CONFIDENCE_THRESHOLD = 0.6
FUZZY_MATCH_THRESHOLD = 70  # thefuzz uses 0-100 scale

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
