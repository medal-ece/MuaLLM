import os
import argparse
import base64
import io
from typing import List, Dict, Any

import numpy as np
from PIL import Image
import chromadb
from unstructured.partition.pdf import partition_pdf
from langchain_chroma import Chroma
from langchain_experimental.open_clip import OpenCLIPEmbeddings
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_openai import ChatOpenAI
from IPython.display import HTML, display
import matplotlib.pyplot as plt
from dotenv import load_dotenv

load_dotenv()

from messages import system_message1

IMAGE_PATH = "figures"
COLLECTION_NAME = "paper1"

def extract_pdf_elements(filename: str) -> List[Any]:
    return partition_pdf(
        filename=filename,
        extract_images_in_pdf=True,
        infer_table_structure=True,
        chunking_strategy="by_title",
        max_characters=4000,
        new_after_n_chars=3800,
        combine_text_under_n_chars=2000,
        image_output_format=IMAGE_PATH,
    )

def categorize_elements(raw_pdf_elements: List[Any]) -> Dict[str, List[str]]:
    tables, texts = [], []
    for element in raw_pdf_elements:
        if "unstructured.documents.elements.Table" in str(type(element)):
            tables.append(str(element))
        else:
            texts.append(str(element))
    return {"tables": tables, "texts": texts}

def setup_vectorstore() -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=OpenCLIPEmbeddings()
    )

def add_elements_to_vectorstore(vectorstore: Chroma, elements: Dict[str, List[str]]) -> None:
    image_uris = sorted([
        os.path.join(IMAGE_PATH, image_name)
        for image_name in os.listdir(IMAGE_PATH)
        if image_name.endswith(".jpg")
    ])
    vectorstore.add_images(uris=image_uris)
    # vectorstore.add_texts(texts=elements["tables"])
    vectorstore.add_texts(texts=elements["texts"])

def resize_base64_image(base64_string: str, size: tuple = (128, 128)) -> str:
    img_data = base64.b64decode(base64_string)
    img = Image.open(io.BytesIO(img_data))
    resized_img = img.resize(size, Image.LANCZOS)
    buffered = io.BytesIO()
    resized_img.save(buffered, format=img.format)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def is_base64(s: str) -> bool:
    try:
        return base64.b64encode(base64.b64decode(s)) == s.encode()
    except Exception:
        return False

def split_image_text_types(docs: List[Any]) -> Dict[str, List[str]]:
    images, text = [], []
    for doc in docs:
        doc = doc.page_content
        if is_base64(doc):
            images.append(resize_base64_image(doc, size=(250, 250)))
        else:
            text.append(doc)
    return {"images": images, "texts": text}

def prompt_func(data_dict: Dict[str, Any]) -> List[HumanMessage]:
    formatted_texts = "\n".join(data_dict["context"]["texts"])
    messages = []

    if data_dict["context"]["images"]:
        image_message = {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{data_dict['context']['images'][0]}"
            },
        }
        messages.append(image_message)

    text_message = {
        "type": "text",
        "text": (
            f"User-provided keywords: {data_dict['question']}\n\n"+
            f"Text and / or tables:\n{formatted_texts}"
        ),
    }
    messages.append(text_message)
    return [HumanMessage(content=messages)]

def setup_rag_pipeline(model: ChatOpenAI, retriever: Any) -> Any:
    return (
        {
            "context": retriever | RunnableLambda(split_image_text_types),
            "question": RunnablePassthrough(),
        }
        | RunnableLambda(prompt_func)
        | model
        | StrOutputParser()
    )

def plt_img_base64(img_base64: str) -> None:
    img_data = base64.b64decode(img_base64)
    img = Image.open(io.BytesIO(img_data))
    
    plt.figure(figsize=(10, 10))
    plt.imshow(img)
    plt.axis('off')
    plt.show()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_path", type=str, default="paper1.pdf")
    parser.add_argument("--query", type=str, required=True)
    args = parser.parse_args()

    raw_pdf_elements = extract_pdf_elements(args.input_path)
    elements = categorize_elements(raw_pdf_elements)

    vectorstore = setup_vectorstore()
    add_elements_to_vectorstore(vectorstore, elements)

    retriever = vectorstore.as_retriever()

    model = ChatOpenAI(temperature=0, model="gpt-4", max_tokens=1024, openai_api_key=os.environ["OPENAI_API_KEY"])
    chain = setup_rag_pipeline(model, retriever)

    response = chain.invoke(args.query)
    print(response)

    docs = retriever.invoke(args.query, k=10)
    for doc in docs:
        if is_base64(doc.page_content):
            print("\nTRUEEEEEEEEEEEE....................\n")
            plt_img_base64(doc.page_content)
        else:
            print(doc.page_content)

if __name__ == "__main__":
    main()



    


    


