"""從市場截圖裡找出每張物品卡片的座標。

用法：python tools/find_positions.py <武陵截圖> <谷地截圖>
截圖從 uploads/ 挑（只保留最近 7 天，見 config.UPLOAD_RETENTION_DAYS）。
"""
import sys

import cv2
import numpy as np

def analyze(path, label):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    print(f"\n=== {label} ({w}x{h}) ===")

    # 轉成灰階
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 物品卡片的底色是白／淺色，所以整列平均亮度高的地方就是卡片所在。
    # 先一列一列掃過去，找出這些「亮帶」。
    row_brightness = np.mean(gray, axis=1)

    # 挑出亮帶（也就是卡片區）
    bright_threshold = 200
    bright_rows = np.where(row_brightness > bright_threshold)[0]

    if len(bright_rows) > 0:
        # 把連在一起的亮列併成同一段
        diffs = np.diff(bright_rows)
        breaks = np.where(diffs > 10)[0]

        regions = []
        start = bright_rows[0]
        for b in breaks:
            end = bright_rows[b]
            if end - start > 50:  # 至少要 50 像素高才算
                regions.append((start, end))
            start = bright_rows[b + 1]
        end = bright_rows[-1]
        if end - start > 50:
            regions.append((start, end))

        print(f"Bright horizontal bands (item card rows):")
        for i, (y1, y2) in enumerate(regions):
            print(f"  Band {i}: y={y1}-{y2} (height={y2-y1})")

    # 再在每條亮帶裡一欄一欄掃，切出單張卡片
    for band_idx, (y1, y2) in enumerate(regions):
        band = gray[y1:y2, :]
        col_brightness = np.mean(band, axis=0)

        # 找卡片的左右邊界（亮的欄）
        bright_cols = np.where(col_brightness > bright_threshold)[0]
        if len(bright_cols) == 0:
            continue

        col_diffs = np.diff(bright_cols)
        col_breaks = np.where(col_diffs > 15)[0]

        cards = []
        cstart = bright_cols[0]
        for b in col_breaks:
            cend = bright_cols[b]
            if cend - cstart > 100:  # At least 100px wide
                cards.append((cstart, cend))
            cstart = bright_cols[b + 1]
        cend = bright_cols[-1]
        if cend - cstart > 100:
            cards.append((cstart, cend))

        print(f"  Band {band_idx} cards:")
        for j, (x1, x2) in enumerate(cards):
            print(f"    Card {j}: x={x1}-{x2}, y={y1}-{y2} ({x2-x1}x{y2-y1})")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    analyze(sys.argv[1], 'Wuling')
    analyze(sys.argv[2], 'Valley IV')
