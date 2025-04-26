from google.cloud import vision
import json
import sys
import os
from dotenv import load_dotenv

load_dotenv()

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/google.json"
def extract_table_from_image(image_path):
    # Initialize the Vision API client
    client = vision.ImageAnnotatorClient()
    
    # Read the image file
    with open(image_path, 'rb') as image_file:
        content = image_file.read()
    
    image = vision.Image(content=content)
    
    # Perform text detection
    response = client.text_detection(image=image)
    texts = response.text_annotations
    
    if not texts:
        return {"error": "No text found in image"}
    
    # Get the full text
    full_text = texts[0].description
    
    # Basic table parsing (you might need to adjust this based on your table structure)
    rows = [row.strip() for row in full_text.split('\n') if row.strip()]
    
    # Try to detect headers (usually first row)
    headers = [h.strip() for h in rows[0].split() if h.strip()]
    
    # Parse data rows
    data = []
    for row in rows[1:]:
        values = [v.strip() for v in row.split() if v.strip()]
        if len(values) == len(headers):
            row_data = dict(zip(headers, values))
            data.append(row_data)
    
    return {
        "headers": headers,
        "data": data,
        "raw_text": full_text  # Including raw text for reference
    }

def main():
    if len(sys.argv) != 2:
        print("Usage: python table.py <path_to_table_image>")
        return
    
    # Check for Google Cloud credentials
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print("Error: GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
        print("Please set it to the path of your Google Cloud service account key file")
        return
    
    image_path = sys.argv[1]
    
    try:
        print(f"\nProcessing table image: {image_path}")
        table_data = extract_table_from_image(image_path)
        
        # Save to JSON file
        output_file = "table.json"
        with open(output_file, 'w') as f:
            json.dump(table_data, f, indent=2)
        
        print(f"Table data saved to {output_file}")
        print("Extracted data preview:")
        print(json.dumps(table_data, indent=2))
        
    except Exception as e:
        print(f"Error processing image: {str(e)}")

if __name__ == "__main__":
    main()
