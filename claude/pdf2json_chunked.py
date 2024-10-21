import json
import uuid
import argparse
import os
from dotenv import load_dotenv
from unstructured.partition.pdf import partition_pdf
import shutil
import glob
import re
import base64
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

load_dotenv()

def is_meaningful(text):
    cleaned_text = re.sub(r'\s', '', text)
    return len(cleaned_text) > 1 and any(char.isalnum() for char in cleaned_text)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def image_summarize(img_base64, prompt):
    chat = ChatOpenAI(model="gpt-4o", max_tokens=1024)
    msg = chat.invoke(
        [
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"},
                    },
                ]
            )
        ]
    )
    return msg.content

def process_pdf(pdf_path, doc_id, output_path, start_number):
    os.makedirs(output_path, exist_ok=True)

    elements = partition_pdf(
        filename=pdf_path,
        extract_images_in_pdf=True,
        infer_table_structure=True,
        strategy="hi_res"
    )

    content = ""
    chunks = []
    images = []
    chunk_id = 0

    for element in elements:
        if hasattr(element, 'text'):
            element_text = element.text.strip()
            if element_text and is_meaningful(element_text):
                chunks.append({
                    "chunk_id": f"doc_{doc_id}_chunk_{chunk_id}",
                    "original_index": chunk_id,
                    "content": element_text
                })
                content += element_text + "\n\n"
                chunk_id += 1

    figures_dir = os.path.join(os.getcwd(), 'figures')
    if os.path.exists(figures_dir):
        image_files = glob.glob(os.path.join(figures_dir, '*'))
        for i, image_file in enumerate(sorted(image_files), start=start_number):
            _, ext = os.path.splitext(image_file)
            new_name = f'image_{i}{ext}'
            new_path = os.path.join(output_path, new_name)
            shutil.move(image_file, new_path)
            
            # Summarize the image
            base64_image = encode_image(new_path)
            prompt = """You are an assistant tasked with summarizing images for retrieval. 
            These summaries will be embedded and used to retrieve the raw image. 
            Give a concise summary of the image that is well optimized for retrieval."""
            summary = image_summarize(base64_image, prompt)
            
            images.append({
                "image_id": f"doc_{doc_id}_image_{i}",
                "path": new_path,
                "summary": summary
            })

        shutil.rmtree(figures_dir)

    document = {
        "doc_id": f"doc_{doc_id}",
        "original_uuid": str(uuid.uuid4().hex),
        "content": content.strip(),
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
