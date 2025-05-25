import os
from pathlib import Path
import anthropic
import fitz  # PyMuPDF
import PIL.Image
import io
import base64
from dotenv import load_dotenv
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from anthropic._exceptions import OverloadedError

load_dotenv()

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=10, max=60),
    retry=retry_if_exception_type(OverloadedError)
)
def extract_image_and_caption(pdf_path, image_path):
    """Process a single image and return its caption from the PDF"""    
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    with open(pdf_path, 'rb') as pdf_file:
        pdf_content = base64.b64encode(pdf_file.read()).decode('utf-8')
    
    with open(image_path, 'rb') as img_file:
        img_content = base64.b64encode(img_file.read()).decode('utf-8')
    
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Please analyze this image and provide a detailed summary in the following format: It is a [type of image] that [brief description of what it shows]. [Detailed description of the image content, including key components, measurements, relationships, and technical significance]. [Explain how this image relates to the paper's main contributions and technical innovations].\n\nFor example, if it's a circuit diagram, describe the key components, their connections, and how they work together. If it's a graph, describe the axes, trends, and what they indicate about the circuit's performance. If it's a block diagram, explain the high-level architecture and how different blocks interact.\n\nMake sure to:\n1. Extract the exact caption from the PDF\n2. Identify the specific type of image (circuit diagram, block diagram, graph, table, etc.)\n3. Provide a comprehensive technical description\n4. Explain the significance of the image in the context of the paper"
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

def process_images_folder(pdf_path, images_folder, output_file):
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
    
    # Get all image files and sort them by name
    image_files = [f for f in images_path.iterdir() if f.suffix.lower() in image_extensions]
    image_files.sort(key=lambda x: int(''.join(filter(str.isdigit, x.stem))))
    
    # Count total eligible images
    total_images = len(image_files)
    print(f"Found {total_images} images to process\n")
    
    # Process each image in the folder
    for idx, image_file in enumerate(image_files, 1):
        print(f"\nProcessing image {idx}/{total_images}: {image_file.name}")
        try:
            # Add longer delay between API calls
            if idx > 1:
                wait_time = 15  # Increased to 15 seconds
                print(f"Waiting {wait_time} seconds before next API call...")
                time.sleep(wait_time)
            
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
            
            # Save progress after each successful image
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=4, ensure_ascii=False)
            print(f"Progress saved to {output_file}")
            
        except Exception as e:
            print(f"✗ Error processing {image_file.name}: {str(e)}\n")
            # Save progress even if there's an error
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=4, ensure_ascii=False)
            print(f"Progress saved to {output_file}")
    
    return results

# Example usage
if __name__ == "__main__":
    import json
    from datetime import datetime
    
    pdf_path = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent3_db/papers/paper2.pdf"
    images_folder = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent3_db/images"
    
    print("Starting image caption extraction process...")
    
    # Create output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent3_db/image_captions.json"
    
    # Process images and get results
    results = process_images_folder(pdf_path, images_folder, output_file)
    
    print(f"\nProcess completed!")
    print(f"Successfully processed {len(results['images'])} images")
    print(f"Results have been saved to: {output_file}")