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


# === 好友價格畫面 ===

# 好友畫面中，左側大物品圖的中心區域 (2560x1440 參考)
# 遊戲介面左邊有暗色邊欄，物品圓圖在白色面板內
FRIEND_ITEM_IMAGE_RECT = {
    'x1': 500, 'y1': 400, 'x2': 780, 'y2': 680,
}

# 好友畫面專用參考圖片目錄
FRIEND_REF_DIR = os.path.join(REF_DIR, 'friend')

# 好友參考圖片快取
_friend_ref_images = {}


def load_friend_reference_images():
    """載入好友畫面專用的參考圖片 (friend/item_N.png)。"""
    global _friend_ref_images
    if _friend_ref_images:
        return _friend_ref_images

    if not os.path.exists(FRIEND_REF_DIR):
        os.makedirs(FRIEND_REF_DIR, exist_ok=True)
        return _friend_ref_images

    for i in range(1, 18):
        path = os.path.join(FRIEND_REF_DIR, f'item_{i}.png')
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is not None:
                _friend_ref_images[i] = img

    if _friend_ref_images:
        print(f"  已載入 {len(_friend_ref_images)} 張好友參考圖片")
    return _friend_ref_images


def save_friend_reference(item_id, crop):
    """儲存好友畫面裁切圖作為未來比對的參考。"""
    os.makedirs(FRIEND_REF_DIR, exist_ok=True)
    path = os.path.join(FRIEND_REF_DIR, f'item_{item_id}.png')
    cv2.imwrite(path, crop)
    # 清除快取，下次重新載入
    global _friend_ref_images
    _friend_ref_images = {}


def match_friend_images(crop, ref_images, region_item_ids=None):
    """
    好友畫面 vs 好友參考圖的比對。
    因為同樣是好友畫面裁切，直接用模板匹配 + 色彩就很準。
    """
    best_id = None
    best_score = -1

    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    ids_to_check = region_item_ids or ref_images.keys()
    scores_debug = []

    for item_id in ids_to_check:
        if item_id not in ref_images:
            continue
        ref = ref_images[item_id]
        ref_resized = cv2.resize(ref, (crop.shape[1], crop.shape[0]))
        ref_gray = cv2.cvtColor(ref_resized, cv2.COLOR_BGR2GRAY)
        ref_hsv = cv2.cvtColor(ref_resized, cv2.COLOR_BGR2HSV)

        # 模板匹配 (同類型圖片，直接比對很準)
        result = cv2.matchTemplate(crop_gray, ref_gray, cv2.TM_CCOEFF_NORMED)
        template_score = result[0][0]

        # HSV 色彩
        h_crop = cv2.calcHist([crop_hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        h_ref = cv2.calcHist([ref_hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(h_crop, h_crop)
        cv2.normalize(h_ref, h_ref)
        color_score = cv2.compareHist(h_crop, h_ref, cv2.HISTCMP_CORREL)

        score = 0.6 * template_score + 0.4 * color_score
        scores_debug.append((item_id, score, template_score, color_score))

        if score > best_score:
            best_score = score
            best_id = item_id

    scores_debug.sort(key=lambda x: x[1], reverse=True)
    for item_id, sc, tpl_s, col_s in scores_debug[:3]:
        print(f"    item_{item_id}: 總={sc:.3f} (模板={tpl_s:.3f}, 色彩={col_s:.3f})")

    return best_id, best_score


def match_item_features(crop, ref_images, region_item_ids=None):
    """
    好友畫面 vs 市場卡片參考圖的比對 (fallback)。
    用 ORB + HSV + 模板匹配綜合。
    """
    best_id = None
    best_score = -1

    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    orb = cv2.ORB_create(nfeatures=500)
    kp1, des1 = orb.detectAndCompute(crop_gray, None)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    ids_to_check = region_item_ids or ref_images.keys()
    scores_debug = []

    for item_id in ids_to_check:
        if item_id not in ref_images:
            continue
        ref = ref_images[item_id]
        ref_resized = cv2.resize(ref, (crop.shape[1], crop.shape[0]))
        ref_gray = cv2.cvtColor(ref_resized, cv2.COLOR_BGR2GRAY)
        ref_hsv = cv2.cvtColor(ref_resized, cv2.COLOR_BGR2HSV)

        # ORB
        kp2, des2 = orb.detectAndCompute(ref_gray, None)
        orb_score = 0.0
        if des1 is not None and des2 is not None and len(des1) > 0 and len(des2) > 0:
            matches = bf.knnMatch(des1, des2, k=2)
            good = []
            for m_pair in matches:
                if len(m_pair) == 2:
                    m, n = m_pair
                    if m.distance < 0.75 * n.distance:
                        good.append(m)
            orb_score = len(good) / max(len(kp1), 1)

        # HSV 色彩
        h_crop = cv2.calcHist([crop_hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        h_ref = cv2.calcHist([ref_hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(h_crop, h_crop)
        cv2.normalize(h_ref, h_ref)
        color_score = cv2.compareHist(h_crop, h_ref, cv2.HISTCMP_CORREL)

        # 模板匹配
        result = cv2.matchTemplate(crop_gray, ref_gray, cv2.TM_CCOEFF_NORMED)
        template_score = result[0][0]

        score = 0.4 * orb_score + 0.25 * color_score + 0.35 * template_score
        scores_debug.append((item_id, score, orb_score, color_score, template_score))

        if score > best_score:
            best_score = score
            best_id = item_id

    scores_debug.sort(key=lambda x: x[1], reverse=True)
    for item_id, sc, orb_s, col_s, tpl_s in scores_debug[:3]:
        print(f"    item_{item_id}: 總={sc:.3f} (ORB={orb_s:.3f}, 色彩={col_s:.3f}, 模板={tpl_s:.3f})")

    return best_id, best_score


def identify_friend_item(screenshot_path, region_hint=None):
    """
    辨識好友價格畫面中左側的大物品圖。
    優先使用好友畫面專用參考圖；若不足則 fallback 到市場卡片參考圖。

    Args:
        screenshot_path: 截圖檔案路徑
        region_hint: 限定比對區域 ('valley_iv' 或 'wuling')

    Returns:
        (item_id, score, region) 或 (None, 0, None)
    """
    img = cv2.imread(screenshot_path)
    if img is None:
        return None, 0, None

    h, w = img.shape[:2]
    scale_x = w / 2560
    scale_y = h / 1440

    rect = FRIEND_ITEM_IMAGE_RECT
    x1 = int(rect['x1'] * scale_x)
    y1 = int(rect['y1'] * scale_y)
    x2 = int(rect['x2'] * scale_x)
    y2 = int(rect['y2'] * scale_y)

    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return None, 0, None

    # 儲存 debug 圖片
    debug_path = os.path.join(REF_DIR, '_debug_friend_crop.png')
    cv2.imwrite(debug_path, crop)

    # 限定比對範圍
    region_ids = None
    if region_hint == 'valley_iv':
        region_ids = list(range(1, 13))
    elif region_hint == 'wuling':
        region_ids = list(range(13, 18))

    # 優先用好友參考圖 (同類型比對，準確度高)
    friend_refs = load_friend_reference_images()
    available_friend = [i for i in (region_ids or range(1, 18)) if i in friend_refs]

    if len(available_friend) >= 3:
        print(f"  使用好友參考圖比對 ({len(available_friend)} 張)")
        item_id, score = match_friend_images(crop, friend_refs, region_ids)
    else:
        # Fallback: 用市場卡片參考圖
        ref_images = load_reference_images()
        if not ref_images:
            print("  警告: 無參考圖片")
            return None, 0, None
        print(f"  使用市場卡片參考圖比對 (好友參考圖不足)")
        item_id, score = match_item_features(crop, ref_images, region_ids)

    # 不再自動覆寫參考圖 — 避免辨識錯誤時污染原始參考圖

    # 判斷區域
    region = region_hint
    if not region and item_id:
        if 1 <= item_id <= 12:
            region = 'valley_iv'
        elif 13 <= item_id <= 17:
            region = 'wuling'

    print(f"  好友畫面物品辨識: item_{item_id} (分數: {score:.3f})")
    return item_id, score, region
