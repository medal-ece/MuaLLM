"""
We will use Unstructured to parse images, text, and tables from documents (PDFs).
We will use the multi-vector retriever with Chroma to store raw text and images along with their summaries for retrieval.
We will use GPT-4o for both image summarization (for retrieval) as well as final answer synthesis from join retrieval of images and text (or tables).
"""

import argparse
from langchain_text_splitters import CharacterTextSplitter
from unstructured.partition.pdf import partition_pdf
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

import base64
import os
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage
import uuid

from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain.storage import InMemoryStore
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

import io
import re

from IPython.display import HTML, display
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from PIL import Image

from unstructured.documents.elements import Image as UnstructuredImage, Text
from typing import List, Any, Tuple

path = "option3_images"
DB_PATH = "option3_db"

def extract_pdf_elements(input):
    """
    Extract images, tables, and chunk text from a PDF file.
    path: File path, which is used to dump images (.jpg)
    """
    return partition_pdf(
        filename=input,
        extract_images_in_pdf=True,
        infer_table_structure=True,
        chunking_strategy="by_title",
        max_characters=4000,
        new_after_n_chars=3800,
        combine_text_under_n_chars=2000,
        image_output_dir_path=path,
    )

def categorize_elements(raw_pdf_elements):
    """
    Categorize extracted elements from a PDF into tables and texts.
    raw_pdf_elements: List of unstructured.documents.elements
    """
    tables = []
    texts = []
    for element in raw_pdf_elements:
        if "unstructured.documents.elements.Table" in str(type(element)):
            tables.append(str(element))
        elif "unstructured.documents.elements.CompositeElement" in str(type(element)):
            texts.append(str(element))
    return texts, tables

def extract_image_captions(raw_pdf_elements) -> List[Tuple[str, str]]:
    """
    Extract image captions from PDF elements.
    
    Args:
    raw_pdf_elements (list): List of elements extracted from the PDF.
    
    Returns:
    list: List of tuples containing figure numbers and their captions.
    """
    image_captions = []
    caption_pattern = re.compile(r'(figure|fig\.?|image|table|diagram)\s*(\d+)\.?\s*([^.]*\.)', re.IGNORECASE)
    
    for element in raw_pdf_elements:
        if hasattr(element, 'text'):
            text = element.text.strip()
            match = caption_pattern.search(text)
            if match:
                figure_num = match.group(2)
                caption = match.group(0)
                image_captions.append((f"Figure {figure_num}", caption))
    
    return image_captions

def generate_text_summaries(texts, tables, summarize_texts=True):
    """
    Summarize text elements
    texts: List of str
    tables: List of str
    summarize_texts: Bool to summarize texts
    """
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
    """Getting the base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def image_summarize(img_base64, prompt):
    """Make image summary"""
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
    """
    Generate summaries and base64 encoded strings for images
    path: Path to list of .jpg files extracted by Unstructured
    image_captions: List of tuples containing figure numbers and their captions
    """
    img_base64_list = []
    image_summaries = []

    prompt = """You are an assistant tasked with summarizing images for retrieval. 
    These summaries will be embedded and used to retrieve the raw image. 
    Give a concise summary of the image that is well optimized for retrieval. 
    Include the figure number and caption in your summary."""

    for i, img_file in enumerate(sorted(os.listdir(path))):
        if img_file.endswith(".jpg"):
            img_path = os.path.join(path, img_file)
            base64_image = encode_image(img_path)
            img_base64_list.append(base64_image)
            
            # Get the corresponding caption if available
            figure_num, caption = image_captions[i] if i < len(image_captions) else (f"Figure {i+1}", "No caption available")
            
            # Include the figure number and caption in the prompt
            figure_prompt = f"{figure_num}: {caption}\n{prompt}"
            summary = image_summarize(base64_image, figure_prompt)
            image_summaries.append(f"{figure_num}: {caption}\n{summary}")

    return img_base64_list, image_summaries

def setup_vectorstore():
    return Chroma(
        collection_name="option3_vectorstore",
        embedding_function=OpenAIEmbeddings(),
        persist_directory=DB_PATH
    )

def create_multi_vector_retriever(
    vectorstore, text_summaries, texts, table_summaries, tables, image_summaries, images
):
    """
    Create retriever that indexes summaries, but returns raw images or texts
    """
    store = InMemoryStore()
    id_key = "doc_id"

    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=store,
        id_key=id_key,
    )

    def add_documents(retriever, doc_summaries, doc_contents):
        doc_ids = [str(uuid.uuid4()) for _ in doc_contents]
        summary_docs = [
            Document(page_content=s, metadata={id_key: doc_ids[i]})
            for i, s in enumerate(doc_summaries)
        ]
        retriever.vectorstore.add_documents(summary_docs)
        retriever.docstore.mset(list(zip(doc_ids, doc_contents)))

    if text_summaries:
        add_documents(retriever, text_summaries, texts)
    if table_summaries:
        add_documents(retriever, table_summaries, tables)
    if image_summaries:
        add_documents(retriever, image_summaries, images)

    return retriever

def plt_img_base64(img_base64):
    """Disply base64 encoded string as image"""
    image_html = f'<img src="data:image/jpeg;base64,{img_base64}" />'
    display(HTML(image_html))

def looks_like_base64(sb):
    """Check if the string looks like base64"""
    return re.match("^[A-Za-z0-9+/]+[=]{0,2}$", sb) is not None

def is_image_data(b64data):
    """
    Check if the base64 data is an image by looking at the start of the data
    """
    image_signatures = {
        b"\xff\xd8\xff": "jpg",
        b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a": "png",
        b"\x47\x49\x46\x38": "gif",
        b"\x52\x49\x46\x46": "webp",
    }
    try:
        header = base64.b64decode(b64data)[:8]  # Decode and get the first 8 bytes
        for sig, format in image_signatures.items():
            if header.startswith(sig):
                return True
        return False
    except Exception:
        return False
    
def resize_base64_image(base64_string, size=(128, 128)):
    """
    Resize an image encoded as a Base64 string
    """
    img_data = base64.b64decode(base64_string)
    img = Image.open(io.BytesIO(img_data))

    resized_img = img.resize(size, Image.LANCZOS)

    buffered = io.BytesIO()
    resized_img.save(buffered, format=img.format)

    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def split_image_text_types(docs):
    """
    Split base64-encoded images and texts
    """
    b64_images = []
    texts = []
    for doc in docs:
        if isinstance(doc, Document):
            doc = doc.page_content
        if looks_like_base64(doc) and is_image_data(doc):
            doc = resize_base64_image(doc, size=(1300, 600))
            b64_images.append(doc)
        else:
            texts.append(doc)
    return {"images": b64_images, "texts": texts}

def img_prompt_func(data_dict):
    """
    Join the context into a single string
    """
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
    """
    Multi-modal RAG chain
    """
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
        raw_pdf_elements = extract_pdf_elements(input_file)
        texts, tables = categorize_elements(raw_pdf_elements)
        image_captions = extract_image_captions(raw_pdf_elements)
        
        # Print extracted captions for debugging
        print("Extracted Image Captions:")
        for figure_num, caption in image_captions:
            print(f"{figure_num}: {caption}")
        
        # write text, tables, and image captions to a file
        with open("results/option3_text_tables_captions.txt", 'w') as f:
            f.write("Texts:\n")
            for text in texts:
                f.write(text + "\n\n")
            f.write("Tables:\n")
            for table in tables:
                f.write(table + "\n\n")
            f.write("Image Captions:\n")
            for figure_num, caption in image_captions:
                f.write(f"{figure_num}: {caption}\n\n")
        
        text_summaries, table_summaries = generate_text_summaries(
            texts, tables, summarize_texts=False
        )
        
        # write text summaries and table summaries to a file
        with open("results/option3_text_summaries.txt", 'w') as f:
            f.write("Text and Caption Summaries:\n")
            for summary in text_summaries:
                f.write(summary + "\n\n")
            f.write("Table Summaries:\n")
            for summary in table_summaries:
                f.write(summary + "\n\n")
        
        img_base64_list, image_summaries = generate_img_summaries(path, image_captions)
        
        # write image summaries to a file
        with open("results/option3_image_summaries.txt", 'w') as f:
            f.write("Image Summaries:\n")
            for summary in image_summaries:
                f.write(f"{summary}\n\n")
        
        retriever = create_multi_vector_retriever(
            vectorstore, text_summaries, texts, table_summaries, tables, image_summaries, img_base64_list
        )
        print(f"Added new content from {input_file} to the database.")
    else:
        print("No input file provided. Using existing database.")
        retriever = create_multi_vector_retriever(
            vectorstore, text_summaries, texts, table_summaries, tables, image_summaries, img_base64_list
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
        with open("results/option3_context_details.txt", 'w') as f:
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