import re
from thefuzz import fuzz, process
from data.items import get_all_item_names_cn
from config import FUZZY_MATCH_THRESHOLD


def parse_ocr_results(ocr_results, items_db):
    """
    Parse raw OCR results into structured (item_name, price) pairs.

    Uses two strategies:
    1. Row-based grouping (works when name and price are on the same line)
    2. Proximity matching fallback (matches names to nearest prices by y-coordinate)

    Args:
        ocr_results: List of dicts with 'text', 'confidence', 'center_y', 'center_x'
        items_db: List of item dicts from database (with 'id', 'name_cn')

    Returns:
        List of dicts: [{"ocr_text", "item_id", "item_name", "price", "confidence"}]
    """
    known_names = get_all_item_names_cn()
    item_name_to_id = {item['name_cn']: item['id'] for item in items_db}

    # First try row-based grouping
    results = _parse_by_rows(ocr_results, known_names, item_name_to_id)

    # Check if we got enough complete pairs (both name and price)
    complete = [r for r in results if r['item_id'] and r['price']]

    if len(complete) >= 3:
        return results

    # Fallback: proximity-based matching (more robust for full window captures)
    proximity_results = _parse_by_proximity(ocr_results, known_names, item_name_to_id)
    prox_complete = [r for r in proximity_results if r['item_id'] and r['price']]

    # Use whichever method found more complete pairs
    if len(prox_complete) >= len(complete):
        return proximity_results
    return results


def _parse_by_rows(ocr_results, known_names, item_name_to_id):
    """Original row-based parsing with increased tolerance."""
    rows = group_by_row(ocr_results, tolerance=50)

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


def _parse_by_proximity(ocr_results, known_names, item_name_to_id):
    """
    Fallback: extract all names and prices separately,
    then match each name to the closest price by y-coordinate.
    """
    if not ocr_results:
        return []

    # Collect all recognized item names with positions
    name_blocks = []
    for block in ocr_results:
        text = block['text'].strip()
        if len(text) < 2:
            continue
        match_result = process.extractOne(
            text, known_names,
            scorer=fuzz.partial_ratio
        )
        if match_result:
            matched_name = match_result[0]
            score = match_result[1]
            if score >= FUZZY_MATCH_THRESHOLD:
                # Avoid duplicates (same item matched multiple times)
                if not any(nb['name'] == matched_name for nb in name_blocks):
                    name_blocks.append({
                        'name': matched_name,
                        'item_id': item_name_to_id.get(matched_name),
                        'center_y': block['center_y'],
                        'center_x': block['center_x'],
                        'confidence': block['confidence'],
                        'ocr_text': text,
                        'score': score,
                    })

    # Collect all valid prices with positions
    price_blocks = []
    for block in ocr_results:
        text = block['text'].strip()
        price_match = re.search(r'^(\d{3,4})$', text)
        if not price_match:
            price_match = re.search(r'(\d{3,4})', text)
            if price_match:
                # Only use if the text is mostly a number (avoid matching % or dates)
                if len(text) > len(price_match.group(0)) + 2:
                    continue
        if price_match:
            val = int(price_match.group(1))
            if 400 <= val <= 6000:
                price_blocks.append({
                    'price': val,
                    'center_y': block['center_y'],
                    'center_x': block['center_x'],
                    'ocr_text': text,
                })

    # Match each name to the closest price by y-coordinate
    results = []
    used_prices = set()

    for nb in sorted(name_blocks, key=lambda x: x['center_y']):
        best_price = None
        best_dist = float('inf')
        best_idx = -1

        for i, pb in enumerate(price_blocks):
            if i in used_prices:
                continue
            dist = abs(nb['center_y'] - pb['center_y'])
            if dist < best_dist:
                best_dist = dist
                best_price = pb
                best_idx = i

        price_val = None
        if best_price and best_dist < 500:  # Max 500px y-distance (for high-res screens)
            price_val = best_price['price']
            used_prices.add(best_idx)

        results.append({
            'ocr_text': nb['ocr_text'],
            'item_id': nb['item_id'],
            'item_name': nb['name'],
            'price': price_val,
            'confidence': nb['confidence'],
        })

    return results


def group_by_row(ocr_results, tolerance=50):
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
