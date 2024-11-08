import base64
import json
import os
from openai import OpenAI
from rich.console import Console
import sys
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO

load_dotenv()

def resize_image(image_path, max_size=(800, 800)):
    """Resize image while maintaining aspect ratio"""
    with Image.open(image_path) as img:
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Calculate new size maintaining aspect ratio
        ratio = min(max_size[0]/img.size[0], max_size[1]/img.size[1])
        new_size = tuple([int(x*ratio) for x in img.size])
        
        # Resize image
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Save to bytes
        buffer = BytesIO()
        resized_img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()

def encode_image(image_path):
    """Convert image to base64 string"""
    # Resize image before encoding
    image_data = resize_image(image_path)
    return base64.b64encode(image_data).decode('utf-8')

def save_json_output(data, output_file):
    """Save JSON with proper formatting"""
    console = Console()
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        
        # Save to file with nice formatting
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        console.print(f"\n[bold red]Error saving JSON:[/bold red] {str(e)}")
        raise

def image_to_structured_json(image_path):
    """Convert table image to structured JSON using GPT-4 Vision"""
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    console = Console()
    
    try:
        base64_image = encode_image(image_path)
        
        messages = [
            {
                "role": "system",
                "content": """You are a specialized assistant that converts table images to structured JSON.
                Follow these guidelines:
                1. Create separate JSON objects for each column in the table
                2. Use the column headers as the main keys in the JSON
                3. For each column, create a detailed object containing all the row information
                4. Handle split cells (like BG/sub-BG) as nested objects within each column
                5. Preserve all numerical values, units, and special characters
                6. Use consistent naming conventions
                7. Handle empty or N/A values appropriately
                8. The output should look like:
                {
                    "this_work": {
                        "cmos_technology": "...",
                        "type": {...},
                        ...
                    },
                    "reference_13": {
                        "cmos_technology": "...",
                        "type": {...},
                        ...
                    },
                    ...
                }
                9. Return ONLY valid JSON without any markdown or explanatory text
                """
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Convert this table to a well-structured JSON format where each column is a separate object."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=4000,
            temperature=0.1
        )
        
        # Extract and clean the response
        content = response.choices[0].message.content.strip()
        
        # Remove any markdown formatting if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        
        # Additional cleaning steps
        content = content.replace("−", "-")
        content = content.replace("μ", "u")
        content = content.replace("\n", "")
        content = content.replace("  ", " ")
        
        try:
            json_response = json.loads(content)
            return json_response
        except json.JSONDecodeError as e:
            # Save the raw response to a debug file
            debug_file = "debug_response.json"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(content)
            console.print(f"\n[bold red]Error parsing JSON:[/bold red] {str(e)}")
            console.print(f"Raw response saved to: {debug_file}")
            raise
            
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {str(e)}")
        raise

def main():
    console = Console()
    
    # Check command line arguments
    if len(sys.argv) != 3:
        console.print("[bold red]Error:[/bold red] Please provide input image path and output JSON path")
        console.print("Usage: python script.py <image_path> <output_json_path>")
        return
    
    # Get paths from command line arguments
    image_path = sys.argv[1]
    output_file = sys.argv[2]
    
    # Verify OpenAI API key
    if not os.getenv('OPENAI_API_KEY'):
        console.print("[bold red]Error:[/bold red] OpenAI API key must be provided via OPENAI_API_KEY environment variable")
        return
    
    # Verify input file exists
    if not os.path.exists(image_path):
        console.print(f"[bold red]Error:[/bold red] Input image not found: {image_path}")
        return
    
    try:
        # Process image and convert to JSON
        json_data = image_to_structured_json(image_path)
        
        # Save results
        save_json_output(json_data, output_file)
        
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {str(e)}")

if __name__ == "__main__":
    main()