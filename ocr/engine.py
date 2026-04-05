import easyocr

_ocr_instance = None


def get_ocr():
    """Get or create EasyOCR reader singleton."""
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = easyocr.Reader(['ch_tra', 'en'], gpu=False)
    return _ocr_instance


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
