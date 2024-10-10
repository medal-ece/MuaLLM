import argparse
from dotenv import load_dotenv
from langchain_unstructured import UnstructuredLoader
import os
import fitz
import io
from PIL import Image
import imagehash
import json
from typing import List, Tuple

load_dotenv()
path = "./data_base/images"
DB_PATH = "./data_base"
openai_api_key = os.environ["OPENAI_API_KEY"]

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

def add_index_to_segments(segments):
    for i, segment in enumerate(segments):
        segment['index'] = i
    return segments

def write_segments_to_file(segments, filename='segments.txt'):
    with open(filename, 'w') as f:
        json.dump(segments, f, indent=2)

def find_caption(image_segment, docs, max_vertical_distance=100, overlap_threshold=0.3):
    image_coords = image_segment['coordinates']['points']
    image_left, image_top = image_coords[0]
    image_right, image_bottom = image_coords[2]
    image_width = image_right - image_left
    image_height = image_bottom - image_top
    image_page = image_segment['page_number']

    potential_captions = []

    for doc in docs:
        if doc.metadata['page_number'] != image_page:
            continue
        
        text_coords = doc.metadata['coordinates']['points']
        text_left, text_top = text_coords[0]
        text_right, text_bottom = text_coords[2]
        text_width = text_right - text_left
        text_height = text_bottom - text_top

        # Check if text is below the image
        if text_top > image_bottom and text_top - image_bottom < max_vertical_distance:
            # Check for horizontal overlap
            overlap = min(image_right, text_right) - max(image_left, text_left)
            overlap_ratio = overlap / min(image_width, text_width)

            if overlap > 0 and overlap_ratio > overlap_threshold:
                # Calculate a score based on position and overlap
                vertical_distance = text_top - image_bottom
                horizontal_center_diff = abs((text_left + text_right) / 2 - (image_left + image_right) / 2)
                
                score = (1 / (vertical_distance + 1)) * overlap_ratio * (1 / (horizontal_center_diff + 1))

                potential_captions.append((doc, score))

    # Sort potential captions by score in descending order
    potential_captions.sort(key=lambda x: x[1], reverse=True)

    # Check the top candidates for caption-like text
    for doc, score in potential_captions[:3]:  # Check top 3 candidates
        text = doc.page_content.strip()
        if text.lower().startswith(('figure', 'fig.', 'fig')):
            return text

    return "Caption not found"

def extract_unique_images_with_captions(pdf_path, segments, docs):
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
            
            image = Image.open(io.BytesIO(image_bytes))
            image_hash = str(imagehash.average_hash(image))
            
            if image_hash not in unique_images:
                unique_images.add(image_hash)
                
                image_filename = f"fig_{figure_count}.png"
                image.save(os.path.join(path, image_filename))
                
                # Find caption for this specific image
                caption = find_caption(segment, docs)
                image_captions[image_filename] = caption
                
                print(f"Saved {image_filename} with caption: {caption[:50]}...")
                figure_count += 1
                
                # Break after processing one image from this segment
                break
    
    doc.close()
    return len(unique_images), image_captions

def extract_tables(docs):
    tables = []
    for doc in docs:
        if doc.metadata.get("category") == "Table":
            tables.append(doc.page_content)
    return tables

def categorize_elements(docs):
    texts = []
    tables = []
    for doc in docs:
        if doc.metadata.get("category") == "Table":
            tables.append(doc.page_content)
        else:
            texts.append(doc.page_content)
    return texts, tables

def main(input_file: str):
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)

    if input_file:
        docs = loader(input_file)
        segments = [doc.metadata for doc in docs]
        segments = add_index_to_segments(segments)
        write_segments_to_file(segments)

        num_unique_images, image_captions = extract_unique_images_with_captions(input_file, segments, docs)
        print(f"{num_unique_images} unique images have been extracted and saved with their captions.")

        texts, tables = categorize_elements(docs)
        
        # Write extracted information to files
        if not os.path.exists("results"):
            os.makedirs("results")
        
        with open("results/extracted_text.txt", 'w') as f:
            for text in texts:
                f.write(f"{text}\n\n")
        
        with open("results/extracted_tables.txt", 'w') as f:
            for table in tables:
                f.write(f"{table}\n\n")
        
        with open("results/image_captions.txt", 'w') as f:
            for image, caption in image_captions.items():
                f.write(f"{image}: {caption}\n\n")
        
        print(f"Extracted content from {input_file} has been saved in the 'results' directory.")
    else:
        print("No input file provided. Please provide a PDF file to process.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to the PDF file", required=True)
    args = parser.parse_args()

    main(args.input)