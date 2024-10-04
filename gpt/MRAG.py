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

def add_index_to_segments(segments):
    for i, segment in enumerate(segments):
        segment['index'] = i
    return segments

def write_segments_to_file(segments, filename='segments.txt'):
    with open(filename, 'w') as f:
        json.dump(segments, f, indent=2)

def parse_segments(segments_file):
    with open(segments_file, 'r') as f:
        segments = json.load(f)
    return segments

def find_caption(segments, image_segment, docs, max_distance=5):
    image_index = image_segment['index']
    image_page = image_segment['page_number']
    image_coords = image_segment['coordinates']
    
    for i in range(image_index + 1, min(image_index + 1 + max_distance, len(segments))):
        segment = segments[i]
        if segment['page_number'] != image_page:
            break  # Stop if we've moved to a different page
        
        if segment['category'] in ['Text', 'Title', 'NarrativeText', "UncategorizedText"]:
            text = next((d.page_content for d in docs if d.metadata.get("index") == i), None)
            if text and text.lower().startswith(('fig', 'figure')):
                # Check if the text is below the image
                if segment['coordinates']['points'][0][1] > image_coords['points'][1][1]:
                    return text
    
    return ''  # Return empty string if no suitable caption is found

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
                
                # Find and store the caption
                caption = find_caption(segments, segment, docs)
                image_captions[image_filename] = caption
                
                print(f"Saved {image_filename} with caption: {caption[:50]}...")  # Print first 50 chars of caption
                figure_count += 1
    
    doc.close()
    
    # Save captions to a JSON file
    with open(os.path.join(path, 'image_captions.json'), 'w') as f:
        json.dump(image_captions, f, indent=2)
    
    return figure_count - 1  # Return the number of unique images extracted

#extract tables
def extract_tables(docs):
    for doc in docs:
        if doc.metadata.get("category") == "Table":
            # write the table to a csv file
            with open(os.path.join(path, 'tables.csv'), 'w') as f:
                f.write(doc.page_content)
    


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_file", type=str, help="Path to the PDF file")
    args = parser.parse_args()
    pdf_file = args.pdf_file
    
    # Load and process the PDF
    docs = loader(pdf_file)
    segments = [doc.metadata for doc in docs]
    
    # Add index to segments
    segments = add_index_to_segments(segments)
    
    # Write segments to file
    write_segments_to_file(segments)
    
    # Extract and save unique images with captions
    num_unique_images = extract_unique_images_with_captions(pdf_file, segments, docs)
    
    print(f"{num_unique_images} unique images have been extracted and saved with their captions.")

    # Extract tables
    extract_tables(docs)
