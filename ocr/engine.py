from paddleocr import PaddleOCR

_ocr_instance = None


def get_ocr():
    """Get or create PaddleOCR singleton instance."""
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang='ch',
            use_gpu=False,
            show_log=False,
        )
    return _ocr_instance


def recognize(image_path):
    """
    Run OCR on an image file.
    Returns list of (bounding_box, text, confidence) tuples.
    """
    ocr = get_ocr()
    result = ocr.ocr(image_path, cls=True)

    parsed = []
    if result and result[0]:
        for line in result[0]:
            bbox = line[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            text = line[1][0]
            confidence = line[1][1]
            # Calculate center y for row grouping
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
