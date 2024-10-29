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
from anthropic import Anthropic
import nltk
from nltk.tokenize import sent_tokenize
nltk.download('punkt', quiet=True)

load_dotenv()

client = Anthropic()

DOCUMENT_CONTEXT_PROMPT = """
<document>
{doc_content}
</document>
"""

CHUNK_CONTEXT_PROMPT = """
Here is the chunk we want to situate within the whole document
<chunk>
{chunk_content}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk.
Answer only with the succinct context and nothing else.
"""

IMAGE_CONTEXT_PROMPT = """
Analyze the provided image in the context of the entire document and provide a caption:

<image>
[A base64 encoded image will be provided here]
</image>

Your tasks:
1. Locate the exact image caption:
   - Thoroughly search the entire document for the precise caption associated with this image.
   - Look for text starting with "Figure", "Fig.", "Table", "Image", "Illustration", or similar, followed by a number or letter (e.g., "Figure 1.2", "Table A").
   - The caption may be anywhere in the document, not necessarily near the image description.
   - If you find a caption, copy it verbatim, preserving all original text, punctuation, and formatting.
   - If multiple captions seem relevant, choose the most likely match based on the image content.
   - If no caption is found, state "No caption found" and briefly describe the image content.

2. Provide concise context:
   - Explain how this image relates to the document's main topics or arguments.
   - Identify key elements in the image that are significant to the document's content.
   - Include relevant keywords or phrases from the document that relate to this image.

Format your response as follows:
Exact Caption: [Verbatim caption from the document, or "No caption found"]
Context: [2-3 sentences of context, including the relationship to the document and search-optimized details]

Important: Ensure the caption is copied exactly as it appears in the document. Do not paraphrase or summarize the caption. The context should enable effective retrieval and understanding of the image within the document's context.
"""

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

def situate_context(doc: str, chunk: str, is_image: bool = False, image_path: str = None) -> str:
    if is_image and image_path:
        base64_image = encode_image(image_path)
        content = [
            {
                "type": "text",
                "text": DOCUMENT_CONTEXT_PROMPT.format(doc_content=doc),
            },
            {
                "type": "text",
                "text": IMAGE_CONTEXT_PROMPT,
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image
                }
            }
        ]
    else:
        content = [
            {
                "type": "text",
                "text": DOCUMENT_CONTEXT_PROMPT.format(doc_content=doc),
                "cache_control": {"type": "ephemeral"}
            },
            {
                "type": "text",
                "text": CHUNK_CONTEXT_PROMPT.format(chunk_content=chunk),
            }
        ]
    
    response = client.beta.prompt_caching.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        temperature=0.0,
        messages=[
            {
                "role": "user", 
                "content": content
            }
        ],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    return response.content[0].text

def create_chunks(text, max_chunk_size=1000, overlap=200):
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
            
            # Add overlap
            overlap_text = " ".join(chunks[-1].split()[-overlap//10:])
            current_chunk = overlap_text + " " + current_chunk
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

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
                content += element_text + "\n\n"

    # Create chunks from the entire content
    text_chunks = create_chunks(content)
    
    for chunk in text_chunks:
        chunks.append({
            "chunk_id": f"doc_{doc_id}_chunk_{chunk_id}",
            "original_index": chunk_id,
            "content": chunk
        })
        chunk_id += 1

    figures_dir = os.path.join(os.getcwd(), 'figures')
    if os.path.exists(figures_dir):
        image_files = glob.glob(os.path.join(figures_dir, '*'))
        for i, image_file in enumerate(sorted(image_files), start=start_number):
            _, ext = os.path.splitext(image_file)
            new_name = f'image_{i}{ext}'
            new_path = os.path.join(output_path, new_name)
            shutil.move(image_file, new_path)
            
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

    # Generate context for text chunks
    for chunk in chunks:
        chunk_context = situate_context(content, chunk['content'])
        chunk['content'] += f"\n\nContext: {chunk_context}"

    # Generate context for images and append to summary
    for image in images:
        image_context = situate_context(content, "", is_image=True, image_path=image['path'])
        image['summary'] += f"\n\n{image_context}"

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
