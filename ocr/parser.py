import re
from thefuzz import fuzz, process
from data.items import get_all_item_names_cn
from config import FUZZY_MATCH_THRESHOLD


def parse_ocr_results(ocr_results, items_db):
    """
    Parse raw OCR results into structured (item_name, price) pairs.

    Args:
        ocr_results: List of dicts with 'text', 'confidence', 'center_y', 'center_x'
        items_db: List of item dicts from database (with 'id', 'name_cn')

    Returns:
        List of dicts: [{"ocr_text", "item_id", "item_name", "price", "confidence"}]
    """
    known_names = get_all_item_names_cn()
    item_name_to_id = {item['name_cn']: item['id'] for item in items_db}

    # Group OCR results by rows (similar y-coordinate)
    rows = group_by_row(ocr_results, tolerance=30)

    results = []
    for row in rows:
        item_name = None
        item_id = None
        price = None
        best_confidence = 0
        ocr_text_parts = []

        for block in row:
            text = block['text'].strip()
            ocr_text_parts.append(text)

            # Try to extract price (3-4 digit number in range 400-6000)
            price_match = re.search(r'(\d{3,4})', text)
            if price_match:
                val = int(price_match.group(1))
                if 400 <= val <= 6000:
                    price = val

            # Try fuzzy matching against known item names
            if len(text) >= 2:
                match_result = process.extractOne(
                    text, known_names,
                    scorer=fuzz.partial_ratio
                )
                if match_result:
                    matched_name = match_result[0]
                    score = match_result[1]
                    if score >= FUZZY_MATCH_THRESHOLD and (item_name is None or score > best_confidence):
                        item_name = matched_name
                        item_id = item_name_to_id.get(matched_name)
                        best_confidence = score

        if price is not None or item_name is not None:
            avg_confidence = sum(b['confidence'] for b in row) / len(row)
            results.append({
                'ocr_text': ' | '.join(ocr_text_parts),
                'item_id': item_id,
                'item_name': item_name or '',
                'price': price,
                'confidence': avg_confidence,
            })

    return results


def group_by_row(ocr_results, tolerance=30):
    """
    Group OCR text blocks by their vertical position (same row).
    Blocks within 'tolerance' pixels of y-center are considered same row.
    """
    if not ocr_results:
        return []

    # Sort by y position
    sorted_results = sorted(ocr_results, key=lambda x: x['center_y'])

    rows = []
    current_row = [sorted_results[0]]

    for block in sorted_results[1:]:
        if abs(block['center_y'] - current_row[0]['center_y']) <= tolerance:
            current_row.append(block)
        else:
            # Sort row by x position
            current_row.sort(key=lambda x: x['center_x'])
            rows.append(current_row)
            current_row = [block]

    if current_row:
        current_row.sort(key=lambda x: x['center_x'])
        rows.append(current_row)

    return rows
