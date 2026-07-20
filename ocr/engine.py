import threading

# 注意：easyocr（連帶 torch）刻意「不」在模組層 import。
# 它是啟動路徑上最重的一塊（乾淨機器首次要十幾秒），模組層 import 會讓
# scanner 的啟動提示視窗遲遲跳不出來。改在真正要建 reader 時才載入。

# 依語言組合快取多個 reader（EasyOCR 規定中/日/韓各自獨立、只能配英文，不能併在同一個 reader）
_readers = {}
_readers_lock = threading.Lock()


def _get_reader(langs):
    """取得（或建立）指定語言組合的 EasyOCR reader 單例。

    加鎖原因：熱鍵在 OCR 預載完成前就已註冊，主執行緒的預載與 worker 的
    掃描可能同時要同一個 reader；無鎖會各自建一個、重複載入模型。"""
    import easyocr  # 延後載入：見檔頭說明
    key = tuple(langs)
    reader = _readers.get(key)
    if reader is not None:
        return reader
    with _readers_lock:
        reader = _readers.get(key)
        if reader is None:
            reader = easyocr.Reader(list(langs), gpu=False)
            _readers[key] = reader
    return reader


def get_ocr():
    """主 reader：繁中 + 英文（市場掃描 / 好友列表的第一道辨識）。"""
    return _get_reader(('ch_tra', 'en'))


def recognize(image_path):
    """
    Run OCR on an image file.
    Returns list of dicts with bbox, text, confidence, center_y, center_x.
    """
    reader = get_ocr()
    result = reader.readtext(image_path)

    parsed = []
    for item in result:
        if len(item) == 3:
            bbox, text, confidence = item
        elif len(item) == 2:
            bbox, text = item
            confidence = 0.0
        else:
            continue
        center_y = (bbox[0][1] + bbox[2][1]) / 2
        center_x = (bbox[0][0] + bbox[2][0]) / 2
        parsed.append({
            'bbox': bbox,
            'text': text,
            'confidence': confidence,
            'center_y': center_y,
            'center_x': center_x,
        })

    return parsed


def recognize_crop(image, bbox, langs, pad=6):
    """
    用指定語言 reader 辨識一塊裁切區域（給好友名稱的日韓回退用）。

    Args:
        image: cv2 影像 (numpy array, BGR)
        bbox: [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] 四角座標（主 reader 給的）
        langs: 例如 ('ja','en') 或 ('ko','en')
        pad: 裁切時往外擴的像素，避免切到字邊

    Returns:
        (text, confidence)；裁切無效或辨識失敗時回 ('', 0.0)
    """
    try:
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        h, w = image.shape[:2]
        x0 = max(0, int(min(xs)) - pad)
        y0 = max(0, int(min(ys)) - pad)
        x1 = min(w, int(max(xs)) + pad)
        y1 = min(h, int(max(ys)) + pad)
        if x1 <= x0 or y1 <= y0:
            return '', 0.0
        crop = image[y0:y1, x0:x1]

        reader = _get_reader(langs)
        result = reader.readtext(crop)
        # 取信心最高的一段當這塊的名字
        best_text, best_conf = '', 0.0
        for item in result:
            if len(item) == 3:
                _, text, conf = item
            elif len(item) == 2:
                _, text = item
                conf = 0.0
            else:
                continue
            if conf >= best_conf:
                best_text, best_conf = text, conf
        return best_text.strip(), best_conf
    except Exception as e:
        # 模型沒下載 / 離線 / 任何 OCR 例外都不能拖垮主掃描流程
        print(f"    [回退 OCR {langs} 失敗] {e}")
        return '', 0.0
