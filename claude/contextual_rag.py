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
        total_chunks = sum(len(doc['chunks']) for doc in dataset)
        
        with tqdm(total=total_chunks, desc="Processing chunks") as pbar:
            for doc in dataset:
                for chunk in doc['chunks']:
                    texts_to_embed.append(chunk['content'])
                    metadata.append({
                        'doc_id': doc['doc_id'],
                        'original_uuid': doc['original_uuid'],
                        'chunk_id': chunk['chunk_id'],
                        'original_index': chunk['original_index'],
                        'content': chunk['content']
                    })
                    pbar.update(1)

        self._embed_and_store(texts_to_embed, metadata)
        self.save_db()
        
        print(f"Vector database loaded and saved. Total chunks processed: {len(texts_to_embed)}")

    def _embed_and_store(self, texts: List[str], data: List[Dict[str, Any]]):
        batch_size = 128
        with tqdm(total=len(texts), desc="Embedding chunks") as pbar:
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


def process_pdfs(pdf_files: List[str]) -> str:
    # Get the directory of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Construct the path to pdf2json.py
    pdf2json_path = os.path.join(current_dir, "pdf2json.py")
    
    # Call pdf2json.py script
    cmd = [sys.executable, pdf2json_path] + pdf_files + ["-o", "data/data.json"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running pdf2json.py: {e}")
        sys.exit(1)
    return "data/data.json"

def main():
    parser = argparse.ArgumentParser(description="Process PDF files and create a vector database")
    parser.add_argument("-i", "--input", nargs="+", required=False, help="PDF files to process")
    parser.add_argument("-o", "--output", default="retrieval.txt", help="Output file for search results")
    args = parser.parse_args()

    # Initialize the VectorDB
    base_db = VectorDB("base_db")

    if args.input:
        # Process PDFs using pdf2json.py
        json_file = process_pdfs(args.input)
        # Load the processed data
        with open(json_file, 'r') as f:
            transformed_dataset = json.load(f)
        
        # Load existing database if it exists
        try:
            base_db.load_db()
            print("Loaded existing vector database.")
        except ValueError:
            print("Creating new vector database.")

        # Append new data to the existing database
        base_db.load_data(transformed_dataset)
    else:
        # If no input PDFs are provided, try to load existing database
        try:
            base_db.load_db()
            print("Loaded existing vector database.")
        except ValueError as e:
            print(f"Error: {e}")
            print("Please provide input PDFs to create a new database.")
            sys.exit(1)

    # Perform a search query
    search_query = "What is nano ampere current reference circuit?"
    search_results = base_db.search(search_query, k=1)

    # Write answer to the search query to a file
    with open(args.output, "w") as f:
        f.write(f"Query: {search_query}\n\n")
        f.write(json.dumps(search_results, indent=2))

    print(f"Search results saved to {args.output}")

if __name__ == "__main__":
    main()
