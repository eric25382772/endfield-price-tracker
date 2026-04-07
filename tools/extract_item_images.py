"""
從市場截圖中提取每個物品的參考圖片。
根據遊戲實際畫面佈局校正。

谷地: 7+5 佈局 (第一行7個, 第二行5個)
武陵: 1行5個, 遊戲畫面順序跟 items.py 不同
"""
import cv2
import os
import sys
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'item_images')
STATIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'images', 'items')

# ========================================
# 遊戲畫面順序 → item_id 對應
# ========================================

# 武陵：遊戲畫面從左到右的順序 → item_id
# item_id 13-17 (database order: 武俠13, 冬蟲14, 武陵凍梨15, 岳研16, 天師龍17)
# 遊戲畫面順序: 武俠, 武陵凍梨, 冬蟲夏筍, 天師龍泡泡, 岳研避瘴茶
WULING_SCREEN_ORDER = [13, 15, 14, 17, 16]

# 四號谷地：遊戲畫面從左到右、上到下
# item_id 1-12, 遊戲順序 = 資料庫順序
# Row 1 (7 items): 錨點1, 懸空2, 巫術3, 天使4, 谷地5, 團結6, 源石7
# Row 2 (5 items): 塞什8, 星體10, 警戒9, 硬頭12, 碎料11
VALLEY_SCREEN_ORDER_ROW1 = [1, 2, 3, 4, 5, 6, 7]
VALLEY_SCREEN_ORDER_ROW2 = [8, 10, 9, 12, 11]


def save_debug_grid(img, cards, labels, output_name):
    """Draw rectangles on image for debugging."""
    debug = img.copy()
    for i, (x1, y1, x2, y2) in enumerate(cards):
        cv2.rectangle(debug, (x1, y1), (x2, y2), (0, 255, 0), 3)
        label = str(labels[i]) if i < len(labels) else str(i)
        cv2.putText(debug, label, (x1+10, y1+30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    path = os.path.join(OUTPUT_DIR, output_name)
    cv2.imwrite(path, debug)
    print(f"  Debug: {path}")


def extract_wuling(screenshot_path):
    """Extract 5 Wuling item images."""
    img = cv2.imread(screenshot_path)
    if img is None:
        print(f"Cannot read {screenshot_path}")
        return
    h, w = img.shape[:2]
    print(f"Wuling: {w}x{h}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 5 items, one row
    card_x_starts = [143, 447, 751, 1055, 1359]
    card_width = 282
    y_top, y_bottom = 680, 920

    cards = []
    for i, item_id in enumerate(WULING_SCREEN_ORDER):
        x1 = card_x_starts[i]
        x2 = x1 + card_width

        cards.append((x1, y_top, x2, y_bottom))
        crop = img[y_top:y_bottom, x1:x2]

        filename = f"item_{item_id}.png"
        cv2.imwrite(os.path.join(OUTPUT_DIR, filename), crop)
        print(f"  screen pos {i+1} -> item_id {item_id}: {filename}")

    save_debug_grid(img, cards, WULING_SCREEN_ORDER, '_debug_wuling.png')


def extract_valley(screenshot_path):
    """Extract 12 Valley IV item images (7+5 layout)."""
    img = cv2.imread(screenshot_path)
    if img is None:
        print(f"Cannot read {screenshot_path}")
        return
    h, w = img.shape[:2]
    print(f"Valley: {w}x{h}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Row 1: 7 items
    row1_x_starts = [143, 447, 751, 1055, 1359, 1663, 1967]
    # Row 2: 5 items
    row2_x_starts = [143, 447, 751, 1055, 1359]
    card_width = 270
    row1_y = (420, 670)
    row2_y = (850, 1100)

    cards = []
    all_ids = []

    # Row 1
    for i, item_id in enumerate(VALLEY_SCREEN_ORDER_ROW1):
        x1 = row1_x_starts[i]
        x2 = x1 + card_width
        y1, y2 = row1_y

        cards.append((x1, y1, x2, y2))
        all_ids.append(item_id)
        crop = img[y1:y2, x1:x2]

        filename = f"item_{item_id}.png"
        cv2.imwrite(os.path.join(OUTPUT_DIR, filename), crop)
        print(f"  R1 pos {i+1} -> item_id {item_id}: {filename}")

    # Row 2
    for i, item_id in enumerate(VALLEY_SCREEN_ORDER_ROW2):
        x1 = row2_x_starts[i]
        x2 = x1 + card_width
        y1, y2 = row2_y

        cards.append((x1, y1, x2, y2))
        all_ids.append(item_id)
        crop = img[y1:y2, x1:x2]

        filename = f"item_{item_id}.png"
        cv2.imwrite(os.path.join(OUTPUT_DIR, filename), crop)
        print(f"  R2 pos {i+1} -> item_id {item_id}: {filename}")

    save_debug_grid(img, cards, all_ids, '_debug_valley.png')


def copy_to_static():
    """Copy item images to static directory."""
    os.makedirs(STATIC_DIR, exist_ok=True)
    # Clean old files
    for f in os.listdir(STATIC_DIR):
        os.remove(os.path.join(STATIC_DIR, f))
    # Copy new files
    count = 0
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith('item_') and f.endswith('.png'):
            shutil.copy2(os.path.join(OUTPUT_DIR, f), os.path.join(STATIC_DIR, f))
            count += 1
    print(f"Copied {count} images to {STATIC_DIR}")


if __name__ == '__main__':
    wuling_path = 'g:/project/uploads/tmpodiqq9_8.png'
    valley_path = 'g:/project/uploads/tmp_f5_f1om.png'

    print("=== Wuling ===")
    extract_wuling(wuling_path)
    print()
    print("=== Valley IV ===")
    extract_valley(valley_path)
    print()
    copy_to_static()
    print("Done!")
