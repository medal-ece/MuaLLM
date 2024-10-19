import json
import uuid
import argparse
import os
from dotenv import load_dotenv
from unstructured.partition.pdf import partition_pdf
import shutil
import glob

load_dotenv()

def process_pdf(pdf_path, doc_id, output_path, start_number):
    # Create the output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)

    # Extract PDF elements
    elements = partition_pdf(
        filename=pdf_path,
        extract_images_in_pdf=True,
        infer_table_structure=True,
        chunking_strategy="by_title",
        max_characters=4000,
        new_after_n_chars=3800,
        combine_text_under_n_chars=2000,
    )

    content = ""
    chunks = []
    images = []

    for i, element in enumerate(elements):
        if hasattr(element, 'text'):
            chunk_text = element.text
            content += chunk_text
            chunk = {
                "chunk_id": f"doc_{doc_id}_chunk_{i}",
                "original_index": i,
                "content": chunk_text
            }
            chunks.append(chunk)

    # Process extracted images
    figures_dir = os.path.join(os.getcwd(), 'figures')
    if os.path.exists(figures_dir):
        image_files = glob.glob(os.path.join(figures_dir, '*'))
        for i, image_file in enumerate(sorted(image_files), start=start_number):
            _, ext = os.path.splitext(image_file)
            new_name = f'image_{i}{ext}'
            new_path = os.path.join(output_path, new_name)
            shutil.move(image_file, new_path)
            images.append({
                "image_id": f"doc_{doc_id}_image_{i}",
                "path": new_path
            })

        # Remove the 'figures' directory
        shutil.rmtree(figures_dir)

    document = {
        "doc_id": f"doc_{doc_id}",
        "original_uuid": str(uuid.uuid4().hex),
        "content": content,
        "chunks": chunks,
        "images": images
    }

    return document, len(images)

def main():
    parser = argparse.ArgumentParser(description="Process PDF files into JSON format")
    parser.add_argument("pdf_files", nargs="+", help="PDF files to process")
    parser.add_argument("-o", "--output", default="output.json", help="Output JSON file")
    parser.add_argument("-i", "--image_dir", default="data/images", help="Directory to save extracted images")
    args = parser.parse_args()

    documents = []
    start_number = 1

    # Get the current highest image number in the output directory
    existing_images = glob.glob(os.path.join(args.image_dir, 'image_*'))
    if existing_images:
        start_number = max([int(os.path.splitext(os.path.basename(f))[0].split('_')[1]) for f in existing_images]) + 1

    for i, pdf_file in enumerate(args.pdf_files, start=1):
        document, num_images = process_pdf(pdf_file, i, args.image_dir, start_number)
        documents.append(document)
        start_number += num_images

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

    print(f"Processed {len(documents)} PDF files. Output saved to {args.output}")
    print(f"Extracted images have been saved to {args.image_dir}")

if __name__ == "__main__":
    main()
