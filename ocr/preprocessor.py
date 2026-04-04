import cv2
import numpy as np


def preprocess_screenshot(image_path, output_path=None):
    """
    Preprocess a game screenshot for better OCR accuracy.
    Returns the path to the preprocessed image.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Apply CLAHE for contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Denoise
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10)

    # Save preprocessed image
    if output_path is None:
        output_path = image_path.rsplit('.', 1)[0] + '_processed.png'
    cv2.imwrite(output_path, denoised)

    return output_path
