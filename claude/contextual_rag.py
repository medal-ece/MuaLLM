import os
import pickle
import json
import numpy as np
import voyageai
from typing import List, Dict, Any
from tqdm import tqdm
from dotenv import load_dotenv
import argparse
import subprocess
import sys
import shutil
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

class VectorDB:
    def __init__(self, name: str, api_key = None):
        if api_key is None:
            api_key = os.getenv("VOYAGE_API_KEY")
        self.client = voyageai.Client(api_key=api_key)
        self.name = name
        self.embeddings = []
        self.metadata = []
        self.query_cache = {}
        self.db_path = f"./data/{name}/vector_db.pkl"

    def load_data(self, dataset: List[Dict[str, Any]]):
        texts_to_embed = []
        metadata = []
        total_chunks = sum(len(doc['chunks']) for doc in dataset) + sum(len(doc['images']) for doc in dataset)
        
        # Load the persistent image data
        with tqdm(total=total_chunks, desc="Processing chunks and images") as pbar:
            for doc in dataset:
                for chunk in doc['chunks']:
                    texts_to_embed.append(chunk['content'])
                    metadata.append({
                        'doc_id': doc['doc_id'],
                        'original_uuid': doc['original_uuid'],
                        'chunk_id': chunk['chunk_id'],
                        'original_index': chunk['original_index'],
                        'content': chunk['content'],
                        'type': 'text'
                    })
                    pbar.update(1)
                
                for image in doc['images']:
                    image_id = image['image_id']
                    texts_to_embed.append(image['summary'])
                    metadata.append({
                        'doc_id': doc['doc_id'],
                        'original_uuid': doc['original_uuid'],
                        'image_id': image_id,
                        'path': image['path'],
                        'summary': image['summary'],
                        'type': 'image'
                    })
                    pbar.update(1)

        self._embed_and_store(texts_to_embed, metadata)
        self.save_db()
        
        print(f"Vector database loaded and saved. Total items processed: {len(texts_to_embed)}")
        print(f"Text chunks: {len([m for m in metadata if m['type'] == 'text'])}")
        print(f"Images: {len([m for m in metadata if m['type'] == 'image'])}")

    def _embed_and_store(self, texts: List[str], data: List[Dict[str, Any]]):
        batch_size = 128
        with tqdm(total=len(texts), desc="Embedding items") as pbar:
            result = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_result = self.client.embed(batch, model="voyage-2").embeddings
                result.extend(batch_result)
                pbar.update(len(batch))
        
        self.embeddings = result
        self.metadata = data

    def search(self, query: str, k: int = 20) -> List[Dict[str, Any]]:
        if query in self.query_cache:
            query_embedding = self.query_cache[query]
        else:
            query_embedding = self.client.embed([query], model="voyage-2").embeddings[0]
            self.query_cache[query] = query_embedding

        if not self.embeddings:
            raise ValueError("No data loaded in the vector database.")

        similarities = np.dot(self.embeddings, query_embedding)
        top_indices = np.argsort(similarities)[::-1][:k]
        
        top_results = []
        for idx in top_indices:
            result = {
                "metadata": self.metadata[idx],
                "similarity": float(similarities[idx]),
            }
            top_results.append(result)
        
        return top_results

    def save_db(self):
        data = {
            "embeddings": self.embeddings,
            "metadata": self.metadata,
            "query_cache": json.dumps(self.query_cache),
        }
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "wb") as file:
            pickle.dump(data, file)

    def load_db(self):
        if not os.path.exists(self.db_path):
            raise ValueError("Vector database file not found. Use load_data to create a new database.")
        with open(self.db_path, "rb") as file:
            data = pickle.load(file)
        self.embeddings = data["embeddings"]
        self.metadata = data["metadata"]
        self.query_cache = json.loads(data["query_cache"])
        print(f"Loaded database with {len(self.metadata)} items")
        print(f"Text chunks: {len([m for m in self.metadata if m['type'] == 'text'])}")
        print(f"Images: {len([m for m in self.metadata if m['type'] == 'image'])}")

def process_pdfs(pdf_files: List[str]) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf2json_path = os.path.join(current_dir, "pdf2json_chunked.py")
    
    cmd = [sys.executable, pdf2json_path] + pdf_files + ["-o", "data/data.json"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running pdf2json.py: {e}")
        sys.exit(1)
    
    return "data/data.json"

def copy_image_to_context(image_path: str, context_folder: str) -> str:
    os.makedirs(context_folder, exist_ok=True)
    filename = os.path.basename(image_path)
    destination = os.path.join(context_folder, filename)
    shutil.copy2(image_path, destination)
    return destination

def extract_image(image_path: str, output_folder: str) -> str:
    os.makedirs(output_folder, exist_ok=True)
    filename = os.path.basename(image_path)
    destination = os.path.join(output_folder, filename)
    
    try:
        shutil.copy2(image_path, destination)
        return destination
    except FileNotFoundError:
        return f"Original image file not found: {image_path}"

def perform_rag(search_query: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Perform Retrieval-Augmented Generation (RAG) using the search results and GPT.
    
    Args:
    search_query (str): The original search query.
    search_results (List[Dict[str, Any]]): The results from the vector search.
    
    Returns:
    str: The generated response.
    """
    # Prepare context from search results
    context = ""
    for result in search_results:
        if result['metadata']['type'] == 'text':
            context += f"Text: {result['metadata']['content']}\n\n"
        elif result['metadata']['type'] == 'image':
            context += f"Image Summary: {result['metadata']['summary']}\n\n"

    # Create a prompt template
    prompt = ChatPromptTemplate.from_template(
        """You are a helpful assistant. Use the provided context to answer the user's query.
        If the answer is not in the context, say you don't know.

        Context:
        {context}

        User Query: {query}

        Assistant: Let me help you with that query based on the information I have."""
    )

    # Create a ChatOpenAI instance
    model = ChatOpenAI(temperature=0, model="gpt-4")

    # Create the RAG chain
    chain = prompt | model | StrOutputParser()

    # Generate the response
    response = chain.invoke({"context": context, "query": search_query})

    return response

def main():
    parser = argparse.ArgumentParser(description="Process PDF files, create a vector database, and perform searches")
    parser.add_argument("-i", "--input", nargs="+", required=False, help="PDF files to process")
    parser.add_argument("-o", "--output", default="retrieval.txt", help="Output file for search results")
    parser.add_argument("-q", "--query", required=False, help="Search query")
    parser.add_argument("-k", "--top_k", type=int, default=5, help="Number of top results to return")
    args = parser.parse_args()

    base_db = VectorDB("base_db")

    if args.input:
        json_file = process_pdfs(args.input)
        with open(json_file, 'r') as f:
            transformed_dataset = json.load(f)
        
        try:
            base_db.load_db()
            print("Loaded existing vector database.")
        except ValueError:
            print("Creating new vector database.")

        base_db.load_data(transformed_dataset)
    else:
        try:
            base_db.load_db()
            print("Loaded existing vector database.")
        except ValueError as e:
            print(f"Error: {e}")
            print("Please provide input PDFs to create a new database.")
            sys.exit(1) 

    if args.query:
        search_query = args.query
    else:
        search_query = input("Enter your search query: ")

    print(f"Searching for: {search_query}")
    search_results = base_db.search(search_query, k=args.top_k)

    # Perform RAG
    generated_response = perform_rag(search_query, search_results)
    print(f"Generated Response: {generated_response}")

    # Write results to output file
    output_folder = "extracted_images"
    with open(args.output, "w") as f:
        f.write(f"Query: {search_query}\n\n")
        f.write("Search Results:\n")
        for i, result in enumerate(search_results, 1):
            f.write(f"{i}. ")
            if result['metadata']['type'] == 'text':
                content = result['metadata']['content'][:500] + "..." if len(result['metadata']['content']) > 500 else result['metadata']['content']
                f.write(f"Text Content: {content}\n")
            elif result['metadata']['type'] == 'image':
                summary = result['metadata']['summary'][:500] + "..." if len(result['metadata']['summary']) > 500 else result['metadata']['summary']
                f.write(f"Image Summary: {summary}\n")
                extracted_image_path = extract_image(result['metadata']['path'], output_folder)
                f.write(f"   Image extracted to: {extracted_image_path}\n")
            f.write(f"   Similarity: {result['similarity']:.4f}\n\n")
        
        f.write("\nGenerated Response:\n")
        f.write(generated_response)

    print(f"Search results and generated response saved to {args.output}")

if __name__ == "__main__":
    main()




