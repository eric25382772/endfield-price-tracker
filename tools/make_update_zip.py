"""打包自動更新檔 `update_vX.Y.zip`，發版時連同 setup.exe 一起上傳 GitHub Release。

內容＝安裝程式會複製的那些程式檔（約 2 MB），不含 Python 本體／套件／OCR 模型——
那些在版本之間不變，所以舊使用者只需抓這包覆蓋即可，不必重跑安裝程式。

用法（專案根目錄）：python tools\\make_update_zip.py
"""
import sys
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from version import __version__  # noqa: E402

# 與 installer/EndfieldTracker.iss 的 [Files] 保持一致；更新檔不含 prices.db 等使用者資料
PATTERNS = [
    '*.py',
    'requirements.txt',
    'start_scanner.bat',
    'templates/**/*',
    'static/**/*',
    'ocr/*.py',
    'tools/**/*',
    'data/*.py',
    'data/item_images/*.png',
    'data/item_images/friend/*.png',
]


def main():
    out = BASE_DIR / f'update_v{__version__}.zip'
    files = []
    for pattern in PATTERNS:
        for path in BASE_DIR.glob(pattern):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            if path.name.startswith('_'):
                continue  # _debug_*.png 是執行時的除錯輸出，不是要發布的資產
            files.append(path)
    files = sorted(set(files))
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(BASE_DIR).as_posix())
    print(f'{out.name}  ({out.stat().st_size / 1048576:.2f} MB, {len(files)} 個檔案)')


if __name__ == '__main__':
    main()
