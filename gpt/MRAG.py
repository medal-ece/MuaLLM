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

def find_caption(image_index, docs, max_distance=3):
    # image_index = image_segment['index']
    # image_page = image_segment['page_number']
    # image_coords = image_segment['coordinates']
    # get the text from just the next segment
    caption = ""
    for i in range(1, max_distance + 1):
        text_index = image_index + i
        text = next((d.page_content for d in docs if d.metadata.get("index") == text_index), None)
        # check if the text is a caption
        if text.lower().startswith(('fig', 'figure')):
            caption = text
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
                caption = find_caption(segment['index'], docs)
                image_captions[image_filename] = caption
                
                print(f"Saved {image_filename} with caption: {caption[:50]}...")  # Print first 50 chars of caption
                figure_count += 1
    
    doc.close()
#extract tables
def extract_tables(docs):
    for doc in docs:
        if doc.metadata.get("category") == "Table":
            # write the table to a csv file
            with open(os.path.join(path, 'tables.csv'), 'w') as f:
                f.write(doc.page_content)
    
# save the text below image
def save_text_below_image(segments, docs):
    i = 1
    max_distance = 2
    for segment in segments:
        caption = ""
        if segment['category'] == 'Image':
            # get the text below the image
            image_index = segment['index']
            # get the text from just the next segment
            text = ""
            for i in range(1, max_distance + 1):
                text_index = image_index + i
                text = next((d.page_content for d in docs if d.metadata.get("index") == text_index), None)
                # check if the text is a caption
                if text.lower().startswith(('fig', 'figure')):
                    caption = text
                    break
    
            # append the caption to a file
            with open(os.path.join(path, 'text_below_image.txt'), 'a') as f:
                f.write(caption)
                f.write("\n")
# test_path="data_base/test_images"
# def extract_images_from_pdf(segments, docs):
#     for segment in segments:
#         if segment['category'] == 'Image':
#             image_index = segment['index']
#             image = next((d.page_content for d in docs if d.metadata.get("index") == image_index), None)
#             print(image)
#             break
#             image.save(os.path.join(test_path, f"image_{image_index}.png"))
                

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
    
    # save the text below image
    save_text_below_image(segments, docs)

    # # extract images from pdf
    # extract_images_from_pdf(segments, docs)
