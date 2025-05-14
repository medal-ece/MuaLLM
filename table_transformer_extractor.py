import torch
import cv2
import numpy as np
from PIL import Image
import pandas as pd
import logging
from pathlib import Path
import argparse
from huggingface_hub import hf_hub_download
from transformers import AutoImageProcessor, TableTransformerForObjectDetection
import matplotlib.pyplot as plt
import fitz  # PyMuPDF

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def extract_table_from_pdf(pdf_path: str, page_number: int = 0, confidence_threshold: float = 0.9) -> pd.DataFrame:
    """
    Extract table from PDF using Table-Transformer.
    
    Args:
        pdf_path (str): Path to PDF file
        page_number (int): Page number to extract table from (0-based)
        confidence_threshold (float): Confidence threshold for table detection
        
    Returns:
        pd.DataFrame: Extracted table as DataFrame
    """
    try:
        # Open PDF and convert page to image
        doc = fitz.open(pdf_path)
        if page_number >= len(doc):
            raise ValueError(f"Page number {page_number} out of range. PDF has {len(doc)} pages.")
        
        page = doc[page_number]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Load model and processor
        image_processor = AutoImageProcessor.from_pretrained("microsoft/table-transformer-detection")
        model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-detection")
        
        # Process image
        inputs = image_processor(images=image, return_tensors="pt")
        outputs = model(**inputs)
        
        # Process predictions
        target_sizes = torch.tensor([image.size[::-1]])
        results = image_processor.post_process_object_detection(
            outputs, threshold=confidence_threshold, target_sizes=target_sizes
        )[0]
        
        # Get table bounding box
        boxes = results["boxes"].cpu().numpy()
        scores = results["scores"].cpu().numpy()
        labels = results["labels"].cpu().numpy()
        
        if len(boxes) == 0:
            raise ValueError("No tables detected in the PDF page")
        
        # Get the highest confidence table
        best_idx = np.argmax(scores)
        table_box = boxes[best_idx]
        
        # Log detection results
        for score, label, box in zip(scores, labels, boxes):
            box = [round(i, 2) for i in box.tolist()]
            logger.info(
                f"Detected {model.config.id2label[label]} with confidence "
                f"{round(score, 3)} at location {box}"
            )
        
        # Convert image to numpy array for processing
        image_np = np.array(image)
        
        # Crop the table region
        x1, y1, x2, y2 = map(int, table_box)
        table_image = image_np[y1:y2, x1:x2]
        
        # Convert to grayscale
        gray = cv2.cvtColor(table_image, cv2.COLOR_RGB2GRAY)
        
        # Apply thresholding
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
        
        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        # Sort contours by y-coordinate
        contours = sorted(contours, key=lambda c: cv2.boundingRect(c)[1])
        
        # Extract cells
        cells = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 20 and h > 20:  # Filter out small noise
                cell_image = table_image[y:y+h, x:x+w]
                # Use pytesseract for text extraction
                import pytesseract
                text = pytesseract.image_to_string(cell_image, config='--psm 6')
                cells.append((y, x, text.strip()))
        
        # Sort cells by row and column
        cells.sort(key=lambda x: (x[0], x[1]))
        
        # Convert to DataFrame
        rows = []
        current_row = []
        current_y = cells[0][0] if cells else 0
        
        for _, _, text in cells:
            if abs(_ - current_y) > 10:  # New row
                if current_row:
                    rows.append(current_row)
                current_row = [text]
                current_y = _
            else:
                current_row.append(text)
        
        if current_row:
            rows.append(current_row)
        
        # Create DataFrame
        df = pd.DataFrame(rows)
        
        # Use first row as header if it exists
        if len(df) > 0:
            df.columns = df.iloc[0]
            df = df[1:]
        
        return df
        
    except Exception as e:
        logger.error(f"Error extracting table from PDF: {str(e)}")
        raise

def save_to_csv(df: pd.DataFrame, output_path: str, **kwargs) -> None:
    """
    Save DataFrame to CSV file.
    
    Args:
        df (pd.DataFrame): DataFrame to save
        output_path (str): Path to save CSV file
        **kwargs: Additional arguments to pass to pd.to_csv()
    """
    try:
        df.to_csv(output_path, index=False, **kwargs)
        logger.info(f"Successfully saved table to {output_path}")
    except Exception as e:
        logger.error(f"Error saving to CSV: {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description='Extract tables from PDFs using Table-Transformer')
    parser.add_argument('--input', required=True, help='Input PDF file path')
    parser.add_argument('--output', required=True, help='Output CSV file path')
    parser.add_argument('--page', type=int, default=0, help='Page number to extract table from (0-based)')
    parser.add_argument('--confidence', type=float, default=0.9, help='Confidence threshold for table detection')
    parser.add_argument('--encoding', default='utf-8', help='Output file encoding')
    parser.add_argument('--delimiter', default=',', help='CSV delimiter')
    
    args = parser.parse_args()
    
    try:
        df = extract_table_from_pdf(args.input, args.page, args.confidence)
        save_to_csv(
            df,
            args.output,
            encoding=args.encoding,
            sep=args.delimiter
        )
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise

if __name__ == '__main__':
    main() 