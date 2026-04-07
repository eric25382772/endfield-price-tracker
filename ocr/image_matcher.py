"""
圖片比對模組 - 用 OpenCV 模板匹配辨識物品
比對截圖中每個卡位的物品圖片與參考圖片，確認是哪個物品
"""
import os
import cv2
import numpy as np

# 參考圖片目錄
REF_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'item_images')

# 卡片佈局 (2560x1440 解析度)
# 四號谷地: 7+5 佈局
VALLEY_CARD_POSITIONS = {
    'row1': {
        'x_starts': [143, 447, 751, 1055, 1359, 1663, 1967],
        'card_width': 270,
        'y_top': 420, 'y_bottom': 670,
    },
    'row2': {
        'x_starts': [143, 447, 751, 1055, 1359],
        'card_width': 270,
        'y_top': 850, 'y_bottom': 1100,
    },
}

# 武陵: 1行5個
WULING_CARD_POSITIONS = {
    'row1': {
        'x_starts': [143, 447, 751, 1055, 1359],
        'card_width': 282,
        'y_top': 680, 'y_bottom': 920,
    },
}

# 參考圖片快取
_ref_images = {}


def load_reference_images():
    """載入所有參考圖片 (item_1.png ~ item_17.png)"""
    global _ref_images
    if _ref_images:
        return _ref_images

    for i in range(1, 18):
        path = os.path.join(REF_DIR, f'item_{i}.png')
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is not None:
                _ref_images[i] = img

    print(f"  已載入 {len(_ref_images)} 張參考圖片")
    return _ref_images


def match_item_image(crop, ref_images, region_item_ids=None):
    """
    用模板匹配比對裁切圖與參考圖片，找出最相似的物品。

    Args:
        crop: 從截圖裁切的物品圖片 (numpy array)
        ref_images: {item_id: image} 參考圖片字典
        region_item_ids: 只比對這些 item_id (限縮搜尋範圍)

    Returns:
        (item_id, score) 最佳匹配的物品 ID 和分數
    """
    best_id = None
    best_score = -1

    # 將裁切圖縮放到跟參考圖一樣大小來比對
    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    ids_to_check = region_item_ids or ref_images.keys()

    for item_id in ids_to_check:
        if item_id not in ref_images:
            continue
        ref = ref_images[item_id]
        ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)

        # 將裁切圖縮放到參考圖大小
        crop_resized = cv2.resize(crop_gray, (ref_gray.shape[1], ref_gray.shape[0]))

        # 用直方圖相關性比較 (對亮度/對比變化更穩健)
        hist_crop = cv2.calcHist([crop_resized], [0], None, [256], [0, 256])
        hist_ref = cv2.calcHist([ref_gray], [0], None, [256], [0, 256])
        cv2.normalize(hist_crop, hist_crop)
        cv2.normalize(hist_ref, hist_ref)
        hist_score = cv2.compareHist(hist_crop, hist_ref, cv2.HISTCMP_CORREL)

        # 結構相似度 (SSIM-like using template matching)
        result = cv2.matchTemplate(crop_resized, ref_gray, cv2.TM_CCOEFF_NORMED)
        template_score = result[0][0]

        # 綜合分數
        score = 0.4 * hist_score + 0.6 * template_score

        if score > best_score:
            best_score = score
            best_id = item_id

    return best_id, best_score


def get_card_positions(region, img_width, img_height):
    """
    取得卡片位置，按解析度縮放。

    Args:
        region: 'valley_iv' 或 'wuling'
        img_width, img_height: 截圖的實際解析度

    Returns:
        List of (x1, y1, x2, y2, center_x, center_y) for each card slot
    """
    ref_w, ref_h = 2560, 1440
    scale_x = img_width / ref_w
    scale_y = img_height / ref_h

    if region == 'valley_iv':
        layout = VALLEY_CARD_POSITIONS
    else:
        layout = WULING_CARD_POSITIONS

    positions = []
    for row_key in sorted(layout.keys()):
        row = layout[row_key]
        for x_start in row['x_starts']:
            x1 = int(x_start * scale_x)
            x2 = int((x_start + row['card_width']) * scale_x)
            y1 = int(row['y_top'] * scale_y)
            y2 = int(row['y_bottom'] * scale_y)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            positions.append((x1, y1, x2, y2, cx, cy))

    return positions


def identify_items_by_image(screenshot_path, region):
    """
    用圖片比對辨識截圖中每個卡位的物品。

    Args:
        screenshot_path: 截圖檔案路徑
        region: 'valley_iv' 或 'wuling'

    Returns:
        List of {
            'item_id': int,
            'match_score': float,
            'card_center_x': int,
            'card_center_y': int,
        }
    """
    ref_images = load_reference_images()
    if not ref_images:
        print("  警告: 無參考圖片，無法進行圖片比對")
        return []

    img = cv2.imread(screenshot_path)
    if img is None:
        print(f"  無法讀取截圖: {screenshot_path}")
        return []

    h, w = img.shape[:2]
    positions = get_card_positions(region, w, h)

    # 限定比對範圍
    if region == 'valley_iv':
        region_ids = list(range(1, 13))  # item 1-12
    else:
        region_ids = list(range(13, 18))  # item 13-17

    results = []
    used_ids = set()

    for idx, (x1, y1, x2, y2, cx, cy) in enumerate(positions):
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        # 排除已匹配的 item_id，避免重複
        available_ids = [i for i in region_ids if i not in used_ids]
        item_id, score = match_item_image(crop, ref_images, available_ids)

        if item_id is not None:
            used_ids.add(item_id)

        results.append({
            'item_id': item_id,
            'match_score': score,
            'card_center_x': cx,
            'card_center_y': cy,
            'slot_index': idx,
        })

        print(f"    卡位{idx+1}: item_{item_id} (分數: {score:.3f})")

    return results
