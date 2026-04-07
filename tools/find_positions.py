"""Find item card positions in market screenshots."""
import cv2
import numpy as np

def analyze(path, label):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    print(f"\n=== {label} ({w}x{h}) ===")

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Save horizontal slices to help identify item positions
    # Items have white/light card backgrounds
    # Look for regions where there are bright rectangular areas

    # Scan rows to find where item cards are (bright horizontal bands)
    row_brightness = np.mean(gray, axis=1)

    # Find bright bands (cards area)
    bright_threshold = 200
    bright_rows = np.where(row_brightness > bright_threshold)[0]

    if len(bright_rows) > 0:
        # Find contiguous bright regions
        diffs = np.diff(bright_rows)
        breaks = np.where(diffs > 10)[0]

        regions = []
        start = bright_rows[0]
        for b in breaks:
            end = bright_rows[b]
            if end - start > 50:  # At least 50px tall
                regions.append((start, end))
            start = bright_rows[b + 1]
        end = bright_rows[-1]
        if end - start > 50:
            regions.append((start, end))

        print(f"Bright horizontal bands (item card rows):")
        for i, (y1, y2) in enumerate(regions):
            print(f"  Band {i}: y={y1}-{y2} (height={y2-y1})")

    # Now scan columns within each band to find individual cards
    for band_idx, (y1, y2) in enumerate(regions):
        band = gray[y1:y2, :]
        col_brightness = np.mean(band, axis=0)

        # Find card boundaries (bright columns)
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


analyze('g:/project/uploads/tmpodiqq9_8.png', 'Wuling')
analyze('g:/project/uploads/tmp_f5_f1om.png', 'Valley IV')
