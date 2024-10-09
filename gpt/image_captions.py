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

def find_caption(image_index, docs, max_distance=3):
    caption = ""
    for i in range(1, max_distance + 1):
        text_index = image_index + i
        text = next((d.page_content for d in docs if d.metadata.get("index") == text_index), None)
        if text and text.lower().startswith(('fig', 'figure')):
            caption = text
            print(i)
            break
    return caption

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
                print(segment['index'])
                caption = find_caption(segment['index'], docs)
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