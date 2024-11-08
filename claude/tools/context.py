import json
import base64
from anthropic import Anthropic
from dotenv import load_dotenv
import uuid
import os
import glob
import shutil
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.text import partition_text
from unstructured.documents.elements import Table, Text

load_dotenv()

client = Anthropic()

DOCUMENT_TITLE_PROMPT = """
Please extract the main title of this academic paper. Return only the title, nothing else.

<document>
{doc_content}
</document>
"""

DOCUMENT_CONTEXT_PROMPT = """
<document>
{doc_content}
</document>
"""

CHUNK_TABLE_PROMPT = """
Here is the chunk we want to find if it contains tabular data:

<chunk>
{chunk_content}
</chunk>
If the text chunk above contains any tabular data not just the explanation of the table content but actual data in table format, answer with "TABLE: Yes". If it does not contain tabular data, answer with "TABLE: No".
"""

CHUNK_CONTEXT_PROMPT = """
Here is the chunk we want to situate within the document:

<chunk>
{chunk_content}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk.
Answer only with the succinct context and nothing else.
"""

IMAGE_TABLE_PROMPT = """
Here is the image we want to find if it contains tabulated data:

<image>
[A base64 encoded image will be provided here]
</image>
If the image is a table, answer with "TABLE: Yes". If it is not a table, answer with "TABLE: No".
"""

IMAGE_CONTEXT_PROMPT = """
Here is the image we want to situate within the document:

<image>
[A base64 encoded image will be provided here]
</image>

Please give a short succinct context to situate this image within the overall document for the purposes of improving search retrieval of the image.
Answer only with the succinct context and nothing else.
"""

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def situate_context(doc: str, chunk: str, is_image: bool = False, image_path: str = None, get_title: bool = False) -> tuple:
    """Returns tuple of (text_response, usage_stats)"""
    if get_title:
        content = [
            {
                "type": "text",
                "text": DOCUMENT_TITLE_PROMPT.format(doc_content=doc),
            }
        ]
    elif is_image and image_path:
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
    return response.content[0].text, response.usage

def load_json(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def process_image(doc_content: str, image_path: str) -> tuple:
    """Process image with three separate model calls"""
    # Check if image exists
    if not os.path.exists(image_path):
        return False, "No caption found", "Image file not found", None
        
    base64_image = encode_image(image_path)
    
    # 1. Check if it's a table
    table_response = client.beta.prompt_caching.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": IMAGE_TABLE_PROMPT},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64_image
                    }
                }
            ]
        }],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    is_table = table_response.content[0].text.strip().lower() == "table: yes"
    
    # 2. Get context
    context_response = client.beta.prompt_caching.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": IMAGE_CONTEXT_PROMPT},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64_image
                    }
                }
            ]
        }],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    context = context_response.content[0].text.strip()
    
    table_type = "image_based" if is_table else None
    
    return is_table, context, table_type

def process_chunk(doc_content: str, chunk_content: str) -> tuple:
    """Process chunk with two separate model calls"""
    
    # 1. Check if it's a table
    table_response = client.beta.prompt_caching.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": CHUNK_TABLE_PROMPT.format(chunk_content=chunk_content)
                }
            ]
        }],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    is_table = table_response.content[0].text.strip().lower() == "table: yes"
    
    # 2. Get context
    context_response = client.beta.prompt_caching.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": CHUNK_CONTEXT_PROMPT.format(chunk_content=chunk_content)
                }
            ]
        }],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
    )
    context = context_response.content[0].text.strip()
    
    table_type = "text_based" if is_table else None
    
    return is_table, context, table_type

def process_documents(json_file_path):
    """Process all documents to add title, context, and table detection"""
    with open(json_file_path, 'r') as f:
        documents = json.load(f)

    for doc in documents:
        print(f"\nProcessing document {doc['doc_id']}...")
        
        # Extract document title
        title_response, title_usage = situate_context(doc['content'], "", get_title=True)
        doc['title'] = title_response.strip()
        print(f"Title: {doc['title']}")
        
        # Process each chunk
        for chunk in doc['chunks']:
            print(f"Processing chunk {chunk['chunk_id']}...")
            is_table, context, table_type = process_chunk(doc['content'], chunk['content'])
            
            chunk['context'] = context
            chunk['document_title'] = doc['title']
            chunk['is_table'] = is_table
            chunk['table_type'] = table_type
            
        # Process each image
        if 'images' in doc:
            for image in doc['images']:
                print(f"Processing image {image['image_id']}...")
                is_table, context, table_type = process_image(doc['content'], image['path'])
                
                image['is_table'] = is_table
                image['context'] = context
                image['table_type'] = table_type
                image['document_title'] = doc['title']

    # Save the updated documents
    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    json_file_path = '../agent_db/documents.json'
    process_documents(json_file_path)
