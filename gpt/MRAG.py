import argparse
from dotenv import load_dotenv
from langchain_unstructured import UnstructuredLoader
import os
import fitz
import io
from PIL import Image
import imagehash
import json
import base64
import re
from typing import List, Tuple

from langchain_text_splitters import CharacterTextSplitter
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage
from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain.storage import InMemoryStore
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

import uuid

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

def generate_text_summaries(texts, tables, summarize_texts=True):
    prompt_text = """You are an assistant tasked with summarizing tables and text for retrieval. \
    These summaries will be embedded and used to retrieve the raw text or table elements. \
    Give a concise summary of the table or text that is well optimized for retrieval. Table or text: {element} """
    prompt = ChatPromptTemplate.from_template(prompt_text)

    model = ChatOpenAI(temperature=0, model="gpt-4o")
    summarize_chain = {"element": lambda x: x} | prompt | model | StrOutputParser()

    text_summaries = []
    table_summaries = []

    if texts and summarize_texts:
        text_summaries = summarize_chain.batch(texts, {"max_concurrency": 5})
    elif texts:
        text_summaries = texts

    if tables:
        table_summaries = summarize_chain.batch(tables, {"max_concurrency": 5})

    return text_summaries, table_summaries

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

def generate_img_summaries(path, image_captions):
    img_base64_list = []
    image_summaries = []

    prompt = """You are an assistant tasked with summarizing images for retrieval. 
    These summaries will be embedded and used to retrieve the raw image. 
    Give a concise summary of the image that is well optimized for retrieval. 
    Include the figure number and caption in your summary."""

    for img_file, caption in image_captions.items():
        img_path = os.path.join(path, img_file)
        base64_image = encode_image(img_path)
        img_base64_list.append(base64_image)
        
        figure_prompt = f"{img_file}: {caption}\n{prompt}"
        summary = image_summarize(base64_image, figure_prompt)
        image_summaries.append(f"{img_file}: {caption}\n{summary}")

    return img_base64_list, image_summaries

def setup_vectorstore():
    embedding_function = OpenAIEmbeddings()
    vectorstore = Chroma(
        collection_name="multi_modal_rag",
        embedding_function=embedding_function,
        persist_directory=DB_PATH,
    )
    return vectorstore

def create_multi_vector_retriever(
    vectorstore, text_summaries, texts, table_summaries, tables, image_summaries, img_base64_list
):
    # Create the multi-vector retriever
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=InMemoryStore(),
    )

    # Add text summaries and full texts
    doc_ids = [str(uuid.uuid4()) for _ in range(len(text_summaries))]
    retriever.vectorstore.add_documents(
        [
            Document(page_content=s, metadata={"doc_id": id})
            for s, id in zip(text_summaries, doc_ids)
        ]
    )
    retriever.docstore.mset(list(zip(doc_ids, texts)))

    # Add table summaries and full tables
    table_ids = [str(uuid.uuid4()) for _ in range(len(table_summaries))]
    retriever.vectorstore.add_documents(
        [
            Document(page_content=s, metadata={"doc_id": id})
            for s, id in zip(table_summaries, table_ids)
        ]
    )
    retriever.docstore.mset(list(zip(table_ids, tables)))

    # Add image summaries and base64 images
    image_ids = [str(uuid.uuid4()) for _ in range(len(image_summaries))]
    retriever.vectorstore.add_documents(
        [
            Document(page_content=s, metadata={"doc_id": id})
            for s, id in zip(image_summaries, image_ids)
        ]
    )
    retriever.docstore.mset(list(zip(image_ids, img_base64_list)))

    return retriever

def looks_like_base64(s):
    return bool(re.match(r'^[A-Za-z0-9+/]*={0,2}$', s))

def is_image_data(b64data):
    image_signatures = {
        b'\xFF\xD8\xFF': 'jpg',
        b'\x89\x50\x4E\x47': 'png',
        b'\x47\x49\x46\x38': 'gif',
        b'\x52\x49\x46\x46': 'webp'
    }
    try:
        header = base64.b64decode(b64data)[:8]
        for sig, format in image_signatures.items():
            if header.startswith(sig):
                return True
        return False
    except Exception:
        return False

def split_image_text_types(docs):
    b64_images = []
    texts = []
    for doc in docs:
        if isinstance(doc, Document):
            doc = doc.page_content
        if looks_like_base64(doc) and is_image_data(doc):
            b64_images.append(doc)
        else:
            texts.append(doc)
    return {"images": b64_images, "texts": texts}

def img_prompt_func(data_dict):
    formatted_texts = "\n".join(data_dict["context"]["texts"])
    messages = []

    if data_dict["context"]["images"]:
        for image in data_dict["context"]["images"]:
            image_message = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            }
            messages.append(image_message)

    text_message = {
        "type": "text",
        "text": (
            "You are a helpful assistant answer related to the user question. \n"
            f"User-provided question: {data_dict['question']}\n\n"
            "Text and / or tables:\n"
            f"{formatted_texts}"
        ),
    }
    messages.append(text_message)
    return [HumanMessage(content=messages)]

def multi_modal_rag_chain(retriever):
    model = ChatOpenAI(temperature=0, model="gpt-4o", max_tokens=1024)

    chain = (
        {
            "context": retriever | RunnableLambda(split_image_text_types),
            "question": RunnablePassthrough(),
        }
        | RunnableLambda(img_prompt_func)
        | model
        | StrOutputParser()
    )

    return chain

def main(input_file: str, query: str):
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)

    vectorstore = setup_vectorstore()

    if input_file:
        docs = loader(input_file)
        segments = [doc.metadata for doc in docs]
        segments = add_index_to_segments(segments)
        write_segments_to_file(segments)

        num_unique_images, image_captions = extract_unique_images_with_captions(input_file, segments, docs)
        print(f"{num_unique_images} unique images have been extracted and saved with their captions.")

        texts, tables = categorize_elements(docs)
        
        text_summaries, table_summaries = generate_text_summaries(texts, tables, summarize_texts=False)
        
        img_base64_list, image_summaries = generate_img_summaries(path, image_captions)
        
        retriever = create_multi_vector_retriever(
            vectorstore, text_summaries, texts, table_summaries, tables, image_summaries, img_base64_list
        )
        print(f"Added new content from {input_file} to the database.")
    else:
        print("No input file provided. Using existing database.")
        retriever = MultiVectorRetriever(
            vectorstore=vectorstore,
            docstore=InMemoryStore(),
            id_key="doc_id",
        )

    chain_multimodal_rag = multi_modal_rag_chain(retriever)
    if query:
        docs = retriever.invoke(query, limit=6)
        result = chain_multimodal_rag.invoke(query)
        print(result)

        # Ensure results directory exists
        if not os.path.exists("results"):
            os.makedirs("results")

        # Save context details to file
        with open("results/context_details.txt", 'w') as f:
            f.write(f"Query: {query}\n\n")
            f.write(f"Answer: {result}\n\n")
            f.write("Context Used:\n")
            
            for i, doc in enumerate(docs):
                if isinstance(doc, Document):
                    content = doc.page_content
                else:
                    content = doc
                
                if looks_like_base64(content) and is_image_data(content):
                    f.write(f"Image {i+1} used in context\n")
                    # Save image
                    img_data = base64.b64decode(content)
                    img = Image.open(io.BytesIO(img_data))
                    img.save(f"results/context_image_{i+1}.jpg")
                else:
                    f.write(f"Text {i+1}: {content}\n\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to the PDF file", required=False)
    parser.add_argument("--query", help="Query to search for", required=True)
    args = parser.parse_args()

    main(args.input, args.query)