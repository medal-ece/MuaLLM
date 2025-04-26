import os
import pickle
import json
import numpy as np
import voyageai
from typing import List, Dict, Any
import dotenv

dotenv.load_dotenv()

class ContextualVectorDB:
    def __init__(self, name: str, voyage_api_key=None):
        if voyage_api_key is None:
            voyage_api_key = os.getenv("VOYAGE_API_KEY")
        self.voyage_client = voyageai.Client()
        self.name = name
        self.embeddings = []
        self.metadata = []
        self.query_cache = {}
        self.db_path = f"/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent2_db/base3_db/vector_db.pkl"
        self.load_db()
    
    def load_db(self):
        """Load existing database if it exists"""
        if os.path.exists(self.db_path):
            with open(self.db_path, "rb") as f:
                data = pickle.load(f)
                self.embeddings = data["embeddings"]
                self.metadata = data["metadata"]
                self.query_cache = json.loads(data["query_cache"])
            print(f"Loaded existing database with {len(self.embeddings)} embeddings")

    def _embed_and_store(self, texts: List[str], data: List[Dict[str, Any]]):
        batch_size = 128
        result = [
            self.voyage_client.embed(
                texts[i : i + batch_size],
                model="voyage-2"
            ).embeddings
            for i in range(0, len(texts), batch_size)
        ]
        new_embeddings = [embedding for batch in result for embedding in batch]
        # Append new embeddings and metadata instead of replacing
        self.embeddings.extend(new_embeddings)
        self.metadata.extend(data)

    def save_db(self):
        data = {
            "embeddings": self.embeddings,
            "metadata": self.metadata,
            "query_cache": json.dumps(self.query_cache)
        }
        
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "wb") as f:
            pickle.dump(data, f)
        
        print(f"Database saved with {len(data['embeddings'])} total embeddings")

def main():
    # Load context.json
    context_path = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent2_db/context2.json"
    with open(context_path, "r") as f:
        context_data = json.load(f)

    # Initialize vector database        
    vector_db = ContextualVectorDB("base3_db")
    
    # Prepare texts to embed and metadata
    texts_to_embed = []
    metadata = []
    
    # Process each item in context data
    for i, item in enumerate(context_data):
        if item["type"] == "text":
            # For text, combine original content with contextualized content
            text_to_embed = f"{item['content']}\n\n{item['contextualized_content']}"
            metadata_item = {
                'doc_id': item['doc_id'],
                'chunk_id': item['chunk_id'],
                'original_content': item['content'],
                'contextualized_content': item['contextualized_content'],
                'original_index': i
            }
        else:  # image type
            # For images, use only contextualized content
            text_to_embed = item['contextualized_content']
            metadata_item = {
                'doc_id': item['doc_id'],
                'image_id': item['image_id'],
                'path': item['path'],
                'contextualized_content': item['contextualized_content'],
                'original_index': i
            }
        
        texts_to_embed.append(text_to_embed)
        metadata.append(metadata_item)
    
    # Create embeddings and store in database
    vector_db._embed_and_store(texts_to_embed, metadata)
    vector_db.save_db()
    
    # Verify the database was created
    db_path = vector_db.db_path
    if os.path.exists(db_path):
        with open(db_path, "rb") as f:
            data = pickle.load(f)
            print(f"Database created successfully with:")
            print(f"- {len(data['embeddings'])} embeddings")
            print(f"- {len(data['metadata'])} metadata items")
            print(f"Database saved at: {db_path}")
    else:
        print(f"Error: Database file not found at {db_path}")

if __name__ == "__main__":
    main() 