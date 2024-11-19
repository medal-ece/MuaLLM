import argparse
import os
import numpy as np
from typing import List, Dict, Any
import json
from PIL import Image
import voyageai
from voyageai.client import Client
import pickle
from dotenv import load_dotenv

load_dotenv()

class ImageDB:
    def __init__(self, name: str = "image_db"):
        self.name = name
        self.client = Client()
        self.embeddings = []
        self.metadata = []
        self.db_path = f"../agent_db/{name}"
        
        # Create directory if it doesn't exist
        os.makedirs(self.db_path, exist_ok=True)
        
        # Load existing database if it exists
        self.load_db()

    def load_db(self):
        """Load existing database if available"""
        embedding_file = os.path.join(self.db_path, "embeddings.pkl")
        metadata_file = os.path.join(self.db_path, "metadata.json")
        
        if os.path.exists(embedding_file) and os.path.exists(metadata_file):
            print(f"Loading existing database from {self.db_path}")
            with open(embedding_file, 'rb') as f:
                self.embeddings = pickle.load(f)
            with open(metadata_file, 'r') as f:
                self.metadata = json.load(f)
            print(f"Loaded {len(self.embeddings)} existing embeddings")

    def save_db(self):
        """Save database to disk"""
        embedding_file = os.path.join(self.db_path, "embeddings.pkl")
        metadata_file = os.path.join(self.db_path, "metadata.json")
        
        with open(embedding_file, 'wb') as f:
            pickle.dump(self.embeddings, f)
        with open(metadata_file, 'w') as f:
            json.dump(self.metadata, f)
        print(f"Database saved to {self.db_path}")

    def add_image(self, image_path: str):
        """Add a single image to the database"""
        try:
            print(f"Processing image: {image_path}")
            
            # Read the image
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            # Get image embedding
            embedding = self.client.embed_image(image_data, model="voyage-2").embeddings[0]
            
            # Get basic image metadata
            img = Image.open(image_path)
            metadata = {
                'path': image_path,
                'filename': os.path.basename(image_path),
                'size': img.size,
                'format': img.format,
                'mode': img.mode
            }
            
            # Add to database
            if not isinstance(self.embeddings, np.ndarray):
                self.embeddings = np.array([embedding])
            else:
                self.embeddings = np.vstack([self.embeddings, embedding])
            self.metadata.append(metadata)
            
            print(f"Successfully added image: {image_path}")
            return True
            
        except Exception as e:
            print(f"Error processing image {image_path}: {e}")
            return False

    def search_similar_images(self, query_image_path: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar images using a query image"""
        try:
            print(f"Searching with query image: {query_image_path}")
            
            # Read and embed query image
            with open(query_image_path, 'rb') as f:
                query_data = f.read()
            query_embedding = self.client.embed_image(query_data, model="voyage-2").embeddings[0]
            
            # Compute similarities
            similarities = np.dot(self.embeddings, query_embedding) / (
                np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
            )
            
            # Get top k results
            top_k_indices = np.argsort(similarities)[-k:][::-1]
            
            results = []
            for idx in top_k_indices:
                results.append({
                    'metadata': self.metadata[idx],
                    'similarity': float(similarities[idx])
                })
            
            return results
            
        except Exception as e:
            print(f"Error during search: {e}")
            return []

def write_results(results: List[Dict[str, Any]], output_file: str = "../agent_db/results/image_search_results.txt"):
    """Write search results to file"""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, "w") as f:
        f.write("Image Search Results:\n\n")
        for i, result in enumerate(results, 1):
            f.write(f"Result {i}:\n")
            f.write(f"Similarity Score: {result['similarity']:.4f}\n")
            f.write("Metadata:\n")
            for key, value in result['metadata'].items():
                f.write(f"  {key}: {value}\n")
            f.write("\n")

def main():
    parser = argparse.ArgumentParser(description="Image embedding and similarity search")
    parser.add_argument("-a", "--add", nargs="+", help="Add images to database")
    parser.add_argument("-s", "--search", help="Search for similar images")
    parser.add_argument("-k", "--top_k", type=int, default=5, help="Number of results to return")
    args = parser.parse_args()

    # Initialize database
    db = ImageDB()

    if args.add:
        print("\nAdding images to database...")
        for image_path in args.add:
            db.add_image(image_path)
        db.save_db()
        print(f"Added {len(args.add)} images to database")

    if args.search:
        print("\nSearching for similar images...")
        results = db.search_similar_images(args.search, k=args.top_k)
        
        print("\nSearch Results:")
        for i, result in enumerate(results, 1):
            print(f"\nResult {i}:")
            print(f"Similarity Score: {result['similarity']:.4f}")
            print("Metadata:")
            for key, value in result['metadata'].items():
                print(f"  {key}: {value}")
        
        # Write results to file
        write_results(results)
        print("\nResults written to: ../agent_db/results/image_search_results.txt")

if __name__ == "__main__":
    main()
