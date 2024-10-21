import json
import base64
from anthropic import Anthropic
from dotenv import load_dotenv
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

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

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
    return response

def load_json(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

# Load JSON data
json_data = load_json('data/data.json')

# Example usage
doc_content = json_data[0]['content']

# Process a text chunk
text_chunk = json_data[0]['chunks'][2]['content']
text_response = situate_context(doc_content, text_chunk)
print(f"Text Chunk Context: {text_response.content[0].text}")

# Process an image chunk
if 'images' in json_data[0] and json_data[0]['images']:
    image_data = json_data[0]['images'][4]
    image_path = image_data['path']
    image_response = situate_context(doc_content, "", is_image=True, image_path=image_path)
    print(f"Image Context (including caption): {image_response.content[0].text}")
else:
    print("No image chunks found in the data.")

# Print cache performance metrics for the last processed chunk
print(f"Input tokens: {image_response.usage.input_tokens}")
print(f"Output tokens: {image_response.usage.output_tokens}")
print(f"Cache creation input tokens: {image_response.usage.cache_creation_input_tokens}")
print(f"Cache read input tokens: {image_response.usage.cache_read_input_tokens}")
