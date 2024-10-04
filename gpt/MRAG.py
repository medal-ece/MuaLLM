import argparse
from dotenv import load_dotenv
from langchain_unstructured import UnstructuredLoader
import os
import fitz
import io
from PIL import Image
import imagehash
import json

load_dotenv()
path = "./data_base/images"
openai_api_key = os.environ["UNSTRUCTURED_API_KEY"]

def loader(pdf_file):
    loader = UnstructuredLoader(
    file_path=pdf_file,
    strategy="hi_res",
    partition_via_api=True,
    coordinates=True,
    )
    docs = []
    for doc in loader.lazy_load():
        docs.append(doc)
    return docs

def parse_segments(segments_file):
    with open(segments_file, 'r') as f:
        segments = eval(f.read())
    return segments

def find_next_text(segments, image_segment):
    image_index = segments.index(image_segment)
    for segment in segments[image_index + 1:]:
        if segment['category'] in ['Text', 'Title', 'NarrativeText']:
            return segment.get('text', '')
    return ''

def extract_unique_images_with_captions(pdf_path, segments):
    doc = fitz.open(pdf_path)
    figure_count = 1
    unique_images = set()
    image_captions = {}
    
    image_segments = [seg for seg in segments if seg['category'] == 'Image']
    
    for segment in image_segments:
        page_num = segment['page_number'] - 1
        page = doc[page_num]
        
        image_list = page.get_images(full=True)
        
        for img in image_list:
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            
            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Compute image hash
            image_hash = str(imagehash.average_hash(image))
            
            # Check if this image is unique
            if image_hash not in unique_images:
                unique_images.add(image_hash)
                
                # Save the image
                image_filename = f"fig_{figure_count}.png"
                image.save(os.path.join(path, image_filename))
                
                # Find and store the caption (next text segment)
                caption = find_next_text(segments, segment)
                image_captions[image_filename] = caption
                
                figure_count += 1
    
    doc.close()
    
    # Save captions to a JSON file
    with open(os.path.join(path, 'image_captions.json'), 'w') as f:
        json.dump(image_captions, f, indent=2)
    
    return figure_count - 1  # Return the number of unique images extracted

def print_unique_categories(segments):
    categories = set(segment['category'] for segment in segments if 'category' in segment)
    print("Unique categories found in segments.txt:")
    for category in sorted(categories):
        print(f"- {category}")
    print()  # Add a blank line for better readability

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_file", type=str, help="Path to the PDF file")
    args = parser.parse_args()
    pdf_file = args.pdf_file
    
    # Load and process the PDF
    docs = loader(pdf_file)
    segments = [doc.metadata for doc in docs]
    
    # Write segments to file
    with open("segments.txt", "w") as f:
        f.write(str(segments))
    
    # Print unique categories
    print_unique_categories(segments)
    
    # Extract and save unique images with captions
    num_unique_images = extract_unique_images_with_captions(pdf_file, segments)
    
    print(f"{num_unique_images} unique images have been extracted and saved with their captions.")