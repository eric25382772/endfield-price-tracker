"""自動更新：啟動時比對 GitHub 最新 release，只抓程式碼就地換檔後重啟。

為什麼不重跑 setup.exe：Python 本體／pip 套件／OCR 模型（約 600 MB）在版本之間不會變，
每次改版真正變動的只有原始碼與樣板（約 2 MB），所以更新只需下載 `update_vX.Y.zip`
覆蓋檔案再重啟，數秒完成——使用者不必再回 GitHub 下載安裝程式。

鐵則：更新失敗一律不影響掃價。任何一步出錯就把備份搬回來、照原本版本繼續跑，
只在網頁上留下提示（state='available'），絕不卡住啟動。
"""
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from config import FRIEND_REF_DIR
from version import __version__

REPO = 'eric25382772/endfield-price-tracker'
API_LATEST = f'https://api.github.com/repos/{REPO}/releases/latest'
RELEASES_PAGE = f'https://github.com/{REPO}/releases/latest'
CHECK_TIMEOUT = 10      # 檢查更新逾時（秒）：連不上就當作沒新版，不能拖住啟動
CHECK_RETRY = 2         # 冷開機第一次連線常較慢，失敗再試一次才判定失敗
DOWNLOAD_TIMEOUT = 90
PIP_TIMEOUT = 1800      # requirements.txt 有變動才會跑，乾淨環境裝套件可能數分鐘

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
STATUS_FILE = DATA_DIR / 'update_status.json'      # 檢查結果；Flask 只讀這份，不自己打 API
APPLIED_FILE = DATA_DIR / 'update_applied.json'    # 一次性標記：重啟後的新版讀到才知道剛更新過
REQUEST_FILE = DATA_DIR / 'update_request.json'    # 網頁按「立即更新」時 Flask 寫，scanner 讀
BACKUP_DIR = DATA_DIR / 'update_backup'            # 換檔前的原檔備份，失敗時搬回來

# 只有這些路徑會被更新檔覆蓋。白名單制：資料庫、log、狀態檔、備份都在 data/ 下，
# 一律不讓更新檔碰到（data/ 只放行 *.py 與 item_images/）。
_ALLOWED_ROOT_SUFFIX = ('.py',)
_ALLOWED_ROOT_FILES = ('requirements.txt', 'start_scanner.bat')
_ALLOWED_DIRS = ('templates/', 'static/', 'ocr/', 'tools/', 'data/item_images/')
# 好友參考圖是固定資產（自動覆寫一旦存錯圖會惡性循環，見 .claude/rules/ocr-scanner.md），
# 只補「本機還沒有」的檔，讓遊戲改版新增的物品拿得到參考圖，但不動已有的。
_NEVER_OVERWRITE_DIR = 'data/item_images/friend/'


def _ver_tuple(s):
    """'v5.10.2' → (5, 10, 2)；缺的位補 0，讓 5.1 與 5.1.0 相等。"""
    nums = re.findall(r'\d+', s or '')[:3]
    return tuple(int(n) for n in nums) + (0,) * (3 - len(nums))


def write_status(**fields):
    """合併寫入 update_status.json（網頁徽章的唯一資料來源）。"""
    data = read_status()
    data.update(fields)
    data['checked_at'] = datetime.now().isoformat(timespec='seconds')
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass


def read_status():
    try:
        return json.loads(STATUS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _take_applied_marker():
    """讀走「剛更新完」的一次性標記，回傳更新前的版號（沒有則 None）。"""
    try:
        old = json.loads(APPLIED_FILE.read_text(encoding='utf-8')).get('from')
        APPLIED_FILE.unlink()
        return old
    except Exception:
        return None


def _ssl_context():
    """優先用 certifi 附的根憑證清單。

    乾淨的 Windows（例如全新 VM）憑證存放區幾乎是空的——Windows 是「用到才上網補」，
    沒瀏覽過網頁就補不到；urllib 走系統存放區於是 CERTIFICATE_VERIFY_FAILED（表面看到的是
    URLError），但同一台機器 pip 卻正常，因為 pip 自帶 certifi。這裡跟 pip 用同一份就不受影響。
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None  # 沒有 certifi 就退回系統預設


def check_latest():
    """問 GitHub 最新 release。連不上會拋例外，由呼叫端當作「沒檢查到」處理。"""
    last = None
    for attempt in range(CHECK_RETRY):
        try:
            return _fetch_latest()
        except Exception as e:
            last = e
            if attempt + 1 < CHECK_RETRY:
                time.sleep(1)
    raise last


def _fetch_latest():
    req = urllib.request.Request(API_LATEST, headers={
        'User-Agent': f'EndfieldTracker/{__version__}',
        'Accept': 'application/vnd.github+json',
    })
    with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT, context=_ssl_context()) as r:
        data = json.loads(r.read().decode('utf-8'))
    zip_url = None
    for asset in data.get('assets') or []:
        name = (asset.get('name') or '').lower()
        if name.startswith('update_') and name.endswith('.zip'):
            zip_url = asset.get('browser_download_url')
            break
    return {
        'latest': (data.get('tag_name') or '').lstrip('vV'),
        'notes': data.get('body') or '',
        'zip_url': zip_url,
    }


def _allowed(name):
    """更新檔裡這個路徑可不可以寫入本機。"""
    if name.endswith('/') or name.startswith('/') or '..' in name or ':' in name:
        return False
    if '/' not in name:
        return name.endswith(_ALLOWED_ROOT_SUFFIX) or name in _ALLOWED_ROOT_FILES
    if name.startswith('data/'):
        return name.startswith('data/item_images/') or name.endswith('.py')
    return name.startswith(_ALLOWED_DIRS)


def _download(url, dest, progress=None):
    req = urllib.request.Request(url, headers={'User-Agent': f'EndfieldTracker/{__version__}'})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT, context=_ssl_context()) as r:
        total = int(r.headers.get('Content-Length') or 0)
        got = 0
        with open(dest, 'wb') as f:
            while True:
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress:
                    mb = got / 1048576
                    detail = (f'下載更新檔… {mb:.1f} / {total / 1048576:.1f} MB'
                              if total else f'下載更新檔… {mb:.1f} MB')
                    pct = 10 + (got / total * 55 if total else 0)
                    progress(None, pct, detail)


def _requirements_changed(zf):
    """更新檔的 requirements.txt 跟本機不同 → 這次更新要順便補裝套件（會多花幾分鐘）。"""
    try:
        new = zf.read('requirements.txt')
    except KeyError:
        return False
    try:
        return new.replace(b'\r\n', b'\n') != (BASE_DIR / 'requirements.txt').read_bytes().replace(b'\r\n', b'\n')
    except Exception:
        return False


def _run_pip():
    subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-r', str(BASE_DIR / 'requirements.txt')],
        cwd=str(BASE_DIR), timeout=PIP_TIMEOUT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _sync_friend_refs():
    """把更新檔帶來的新好友參考圖補進實際讀取的目錄（安裝版在 %LOCALAPPDATA%）。
    同名檔不覆蓋——使用者手上那份才是準的。"""
    src = DATA_DIR / 'item_images' / 'friend'
    dst = Path(FRIEND_REF_DIR)
    if not src.is_dir() or src.resolve() == dst.resolve():
        return
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for png in src.glob('*.png'):
            if not (dst / png.name).exists():
                shutil.copy2(png, dst / png.name)
    except Exception:
        pass


def _apply_zip(zip_path, progress=None):
    """把更新檔覆蓋到程式目錄。失敗就把備份搬回來，回傳 False。"""
    with zipfile.ZipFile(zip_path) as zf:
        members = [n for n in zf.namelist() if _allowed(n)]
        # 認得出這是本專案的更新檔才動手，避免抓到不相干的 zip 把程式目錄搞爛
        if 'scanner.py' not in members or 'app.py' not in members:
            return False
        need_pip = _requirements_changed(zf)
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        done = []
        try:
            for name in members:
                target = BASE_DIR / name
                if name.startswith(_NEVER_OVERWRITE_DIR) and target.exists():
                    continue
                if target.exists():
                    backup = BACKUP_DIR / name
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, 'wb') as out:
                    shutil.copyfileobj(src, out)
                done.append(name)
        except Exception:
            for name in done:  # 還原：只搬回這次真的動過的檔
                backup = BACKUP_DIR / name
                if backup.exists():
                    try:
                        shutil.copy2(backup, BASE_DIR / name)
                    except Exception:
                        pass
            return False
    if progress:
        progress(None, 80, '套用更新檔…')
    _sync_friend_refs()
    if need_pip:
        if progress:
            progress(None, 85, '安裝新套件，可能要幾分鐘…')
        try:
            _run_pip()
        except Exception:
            pass  # 套件沒裝成功不回滾程式碼：舊套件多半仍能跑，網頁會顯示版本狀態
    return True


def apply_update(info, progress=None):
    """下載並套用更新。成功回傳 True（呼叫端接著重啟），失敗回傳 False（照舊版繼續跑）。"""
    tmp = Path(tempfile.gettempdir()) / f'endfield_update_{info["latest"]}.zip'
    try:
        _download(info['zip_url'], tmp, progress)
        if not _apply_zip(tmp, progress):
            return False
    except Exception:
        return False
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        APPLIED_FILE.write_text(json.dumps({
            'from': __version__, 'to': info['latest'],
            'ts': datetime.now().isoformat(timespec='seconds'),
        }, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass
    return True


def pending_update():
    """狀態檔裡是否有「可更新但還沒套用」的版本（給網頁按鈕的補救路徑用）。"""
    st = read_status()
    if st.get('state') == 'available' and st.get('zip_url'):
        return {'latest': st.get('latest'), 'zip_url': st['zip_url'], 'notes': st.get('notes', '')}
    return None


def restart():
    """用新版重新啟動自己（不返回）。

    重啟才會載入新的程式碼，所以啟動提示視窗會關掉再開一次（一關一開，不是兩個並存）。
    """
    subprocess.Popen([sys.executable, str(BASE_DIR / 'scanner.py')], cwd=str(BASE_DIR))
    os._exit(0)


def startup_update(progress=None):
    """啟動時檢查並套用更新。回傳 True 表示已更新完、呼叫端應立刻重啟。

    設計決策（v5.1 定案）：完全自動，不問使用者；只在啟動時檢查一次。
    """
    updated_from = _take_applied_marker()
    try:
        info = check_latest()
    except Exception as e:
        # 只記型別（URLError）看不出真因，把底層原因一起寫進狀態與 log
        reason = getattr(e, 'reason', None) or e
        print(f"  [檢查更新失敗] {type(e).__name__}: {reason}")
        traceback.print_exc()
        write_status(current=__version__, latest=None, state='error', zip_url=None,
                     message=f'連不上 GitHub：{reason}'[:200], updated_from=updated_from)
        return False

    if _ver_tuple(info['latest']) <= _ver_tuple(__version__):
        write_status(current=__version__, latest=info['latest'], state='latest',
                     zip_url=None, message='', notes='', updated_from=updated_from)
        return False

    if not info['zip_url']:
        # 該版沒附快速更新檔（例如需要重裝套件的大改版）→ 只提示，請他去 GitHub 下載安裝程式
        write_status(current=__version__, latest=info['latest'], state='available', zip_url=None,
                     notes=info['notes'], updated_from=updated_from,
                     message='這個版本要用安裝程式更新，請到 GitHub 下載')
        return False

    if progress:
        progress(f'發現新版本 v{info["latest"]}，正在自動更新', 10, '準備下載更新檔…')
    if not apply_update(info, progress):
        write_status(current=__version__, latest=info['latest'], state='available',
                     zip_url=info['zip_url'], notes=info['notes'], updated_from=updated_from,
                     message='自動更新沒成功，仍以目前版本執行')
        return False

    write_status(current=__version__, latest=info['latest'], state='updating',
                 zip_url=None, message='', notes=info['notes'])
    if progress:
        progress(f'已更新到 v{info["latest"]}', 100, '重新啟動中…')
    return True
