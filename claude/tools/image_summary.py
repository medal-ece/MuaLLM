import os
from pathlib import Path
import anthropic
import fitz  # PyMuPDF
import PIL.Image
import io
import base64
from dotenv import load_dotenv

load_dotenv()

def extract_image_and_caption(pdf_path, image_path):
    """Process a single image and return its caption from the PDF"""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    with open(pdf_path, 'rb') as pdf_file:
        pdf_content = base64.b64encode(pdf_file.read()).decode('utf-8')
    
    with open(image_path, 'rb') as img_file:
        img_content = base64.b64encode(img_file.read()).decode('utf-8')
    
    message = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Please find this image in the PDF document and extract only the caption. Return only the caption text."
                },
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_content
                    },
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": img_content
                    }
                },
            ]
        }]
    )
    
    # Print usage information
    print("API Usage Info:")
    print(message.usage.model_dump_json(indent=2))
    print()
    
    return message.content[0].text

def process_images_folder(pdf_path, images_folder):
    """Process all images in a folder and return their captions"""
    print(f"\nProcessing images from folder: {images_folder}")
    print(f"Using PDF: {pdf_path}\n")
    
    results = {
        "pdf_path": pdf_path,
        "images": []
    }
    images_path = Path(images_folder)
    
    # Supported image formats
    image_extensions = ('.jpg', '.jpeg', '.png')
    
    # Count total eligible images
    total_images = sum(1 for f in images_path.iterdir() if f.suffix.lower() in image_extensions)
    print(f"Found {total_images} images to process\n")
    
    # Process each image in the folder
    for idx, image_file in enumerate(images_path.iterdir(), 1):
        if image_file.suffix.lower() in image_extensions:
            print(f"\nProcessing image {idx}/{total_images}: {image_file.name}")
            try:
                caption = extract_image_and_caption(pdf_path, str(image_file))
                print("\nCaption content:")
                print("-" * 50)
                print(caption)
                print("-" * 50)
                
                image_data = {
                    "image_path": str(image_file),
                    "caption": caption
                }
                results["images"].append(image_data)
                print(f"✓ Successfully processed {image_file.name}\n")
            except Exception as e:
                print(f"✗ Error processing {image_file.name}: {str(e)}\n")
    
    return results

# Example usage
if __name__ == "__main__":
    import json
    from datetime import datetime
    
    pdf_path = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/papers/paper1.pdf"
    images_folder = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent2_db/images"
    
    print("Starting image caption extraction process...")
    
    # Process images and get results
    results = process_images_folder(pdf_path, images_folder)
    
    # Create output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent2_db/image_captions_paper1.json"
    
    # Save results to JSON file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    
    print(f"\nProcess completed!")
    print(f"Successfully processed {len(results['images'])} images")
    print(f"Results have been saved to: {output_file}")
