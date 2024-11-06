import os
import pickle
import json
import numpy as np
import voyageai
from typing import List, Dict, Any, Callable, Tuple
from tqdm import tqdm
from dotenv import load_dotenv
import argparse
import subprocess
import sys
import shutil
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import cohere
import time

load_dotenv()

class ElasticsearchBM25:
    def __init__(self, index_name: str = "contextual_bm25_index"):
        self.es_client = Elasticsearch("http://localhost:9200")
        self.index_name = index_name
        self.create_index()

    def create_index(self):
        index_settings = {
            "settings": {
                "analysis": {"analyzer": {"default": {"type": "english"}}},
                "similarity": {"default": {"type": "BM25"}},
                "index.queries.cache.enabled": False
            },
            "mappings": {
                "properties": {
                    "content": {"type": "text", "analyzer": "english"},
                    "contextualized_content": {"type": "text", "analyzer": "english"},
                    "doc_id": {"type": "keyword", "index": False},
                    "chunk_id": {"type": "keyword", "index": False},
                    "original_index": {"type": "integer", "index": False},
                }
            },
        }
        if not self.es_client.indices.exists(index=self.index_name):
            self.es_client.indices.create(index=self.index_name, body=index_settings)
            print(f"Created index: {self.index_name}")

    def index_documents(self, documents: List[Dict[str, Any]]):
        actions = [
            {
                "_index": self.index_name,
                "_source": {
                    "content": doc["original_content"],
                    "contextualized_content": doc["contextualized_content"],
                    "doc_id": doc["doc_id"],
                    "chunk_id": doc["chunk_id"],
                    "original_index": doc["original_index"],
                },
            }
            for doc in documents
        ]
        success, _ = bulk(self.es_client, actions)
        self.es_client.indices.refresh(index=self.index_name)
        return success

    def search(self, query: str, k: int = 20) -> List[Dict[str, Any]]:
        self.es_client.indices.refresh(index=self.index_name)
        search_body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["content", "contextualized_content"],
                }
            },
            "size": k,
        }
        response = self.es_client.search(index=self.index_name, body=search_body)
        return [
            {
                "doc_id": hit["_source"]["doc_id"],
                "content": hit["_source"]["content"],
                "contextualized_content": hit["_source"]["contextualized_content"],
                "score": hit["_score"],
            }
            for hit in response["hits"]["hits"]
        ]

def chunk_to_content(chunk: Dict) -> str:
    """Convert a chunk to its content string."""
    # Check if it's an image chunk
    if 'image_id' in chunk['metadata']:
        return chunk['metadata'].get('summary', '') + '\n\n' + chunk['metadata'].get('context', '')
    
    # For text chunks, return the full content which includes both content and context
    return chunk['metadata'].get('content', '')

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
        self.es_bm25 = ElasticsearchBM25(f"{name}_bm25_index")

    def load_data(self, dataset: List[Dict[str, Any]]):
        texts_to_embed = []
        metadata = []
        total_chunks = sum(len(doc['chunks']) for doc in dataset) + sum(len(doc['images']) for doc in dataset)
        
        # Process chunks and images
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

        # Embed and store data
        self._embed_and_store(texts_to_embed, metadata)
        
        # Index documents in Elasticsearch
        documents = []
        for doc in dataset:
            for chunk in doc['chunks']:
                documents.append({
                    'original_content': chunk['content'],
                    'contextualized_content': chunk['content'],
                    'doc_id': doc['doc_id'],
                    'chunk_id': chunk['chunk_id'],
                    'original_index': chunk['original_index']
                })
        
        self.es_bm25.index_documents(documents)
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
        # Get query embedding
        if query in self.query_cache:
            query_embedding = self.query_cache[query]
        else:
            query_embedding = self.client.embed([query], model="voyage-2").embeddings[0]
            self.query_cache[query] = query_embedding

        if not self.embeddings:
            raise ValueError("No embeddings found. Please load data first.")

        # Calculate cosine similarities
        similarities = np.dot(self.embeddings, query_embedding) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        # Get top k indices
        top_k_indices = np.argsort(similarities)[-k:][::-1]
        
        # Format results
        results = []
        for idx in top_k_indices:
            results.append({
                'metadata': self.metadata[idx],
                'similarity': float(similarities[idx])  # Convert to float for JSON serialization
            })
        
        return results

    def combine_results(self, semantic_results, bm25_results, k, 
                       semantic_weight=0.8, bm25_weight=0.2):
        combined_scores = {}
        
        # Process semantic results
        for i, result in enumerate(semantic_results):
            # Check if metadata exists and has required fields
            if 'metadata' in result and 'doc_id' in result['metadata']:
                doc_id = result['metadata']['doc_id']
                combined_scores[doc_id] = {
                    'score': semantic_weight * (1 / (i + 1)),
                    'metadata': result['metadata'],
                    'from_semantic': True,
                    'from_bm25': False
                }

        # Process BM25 results
        for i, result in enumerate(bm25_results):
            doc_id = result['doc_id']
            score = bm25_weight * (1 / (i + 1))
            
            if doc_id in combined_scores:
                combined_scores[doc_id]['score'] += score
                combined_scores[doc_id]['from_bm25'] = True
            else:
                # Find matching metadata from semantic results
                matching_metadata = next(
                    (r['metadata'] for r in semantic_results if r['metadata']['doc_id'] == doc_id),
                    None
                )
                if matching_metadata:
                    combined_scores[doc_id] = {
                        'score': score,
                        'metadata': matching_metadata,
                        'from_semantic': False,
                        'from_bm25': True
                    }

        # Sort by score and return top k results
        sorted_results = sorted(
            combined_scores.items(), 
            key=lambda x: x[1]['score'], 
            reverse=True
        )[:k]
        
        return [
            {
                'metadata': item[1]['metadata'], 
                'similarity': item[1]['score']
            } 
            for item in sorted_results
        ]

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

    def search_with_rerank(self, query: str, k: int = 20) -> List[Dict[str, Any]]:
        """Perform search with Cohere reranking."""
        co = cohere.Client(os.getenv("COHERE_API_KEY"))
        
        # Get initial results
        semantic_results = self.search(query, k=k*10)
        
        # Prepare documents for reranking
        documents = [chunk_to_content(res) for res in semantic_results]

        # Perform reranking
        response = co.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=documents,
            top_n=k
        )
        time.sleep(0.1)  # Rate limiting
        
        # Process reranked results
        final_results = []
        for r in response.results:
            original_result = semantic_results[r.index]
            final_results.append({
                "metadata": original_result['metadata'],
                "similarity": r.relevance_score
            })
        
        return final_results

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

def extract_image(image_path: str, output_folder: str, model_info: str = None) -> Dict[str, str]:
    """Extract image and return both path and model info"""
    os.makedirs(output_folder, exist_ok=True)
    filename = os.path.basename(image_path)
    destination = os.path.join(output_folder, filename)
    
    try:
        shutil.copy2(image_path, destination)
        return {
            "path": destination,
            "model": model_info if model_info else "Unknown"
        }
    except FileNotFoundError:
        return {
            "path": f"Original image file not found: {image_path}",
            "model": "Error"
        }

def perform_rag(search_query: str, search_results: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    """
    Perform RAG using combined semantic and BM25 search results.
    Returns the generated response and list of images used.
    """
    context = ""
    used_images = []
    
    for result in search_results:
        try:
            if 'metadata' not in result:
                continue
                
            metadata = result['metadata']
            if metadata.get('type') == 'text':
                context += f"Text: {metadata.get('content', '')}\n\n"
            elif metadata.get('type') == 'image':
                image_path = metadata.get('path', '')
                if image_path:
                    used_images.append(image_path)
                context += f"Image Summary: {metadata.get('summary', '')}\n\n"
                
            similarity = result.get('similarity', 0)
            context += f"Relevance Score: {similarity:.4f}\n\n"
            
        except Exception as e:
            print(f"Error processing result: {e}")
            continue

    prompt = ChatPromptTemplate.from_template(
        """You are a helpful assistant. Use the provided context to answer the user's query.
        If the answer is not in the context, say you don't know.
        If you reference any figures or images in your response, please explicitly indicate 
        which image file contains that figure (e.g., "This circuit is shown in <image_path>").

        Context:
        {context}

        User Query: {query}

        Assistant: Let me help you with that query based on the information I have."""
    )

    model = ChatOpenAI(temperature=0, model="gpt-4")
    chain = prompt | model | StrOutputParser()
    response = chain.invoke({"context": context, "query": search_query})

    return response, used_images

def evaluate_retrieval_rerank(queries: List[Dict[str, Any]], 
                            retrieval_function: Callable, 
                            db, 
                            k: int = 20) -> Dict[str, float]:
    """Evaluate retrieval with reranking."""
    total_score = 0
    total_queries = len(queries)
    
    for query_item in tqdm(queries, desc="Evaluating retrieval"):
        query = query_item['query']
        golden_chunk_uuids = query_item['golden_chunk_uuids']
        
        golden_contents = []
        for doc_uuid, chunk_index in golden_chunk_uuids:
            golden_doc = next((doc for doc in query_item['golden_documents'] 
                             if doc['uuid'] == doc_uuid), None)
            if golden_doc:
                golden_chunk = next((chunk for chunk in golden_doc['chunks'] 
                                   if chunk['index'] == chunk_index), None)
                if golden_chunk:
                    golden_contents.append(golden_chunk['content'].strip())
        
        if not golden_contents:
            print(f"Warning: No golden contents found for query: {query}")
            continue
        
        retrieved_docs = retrieval_function(query, db, k)
        
        chunks_found = 0
        for golden_content in golden_contents:
            for doc in retrieved_docs[:k]:
                retrieved_content = doc['metadata']['original_content'].strip()
                if retrieved_content == golden_content:
                    chunks_found += 1
                    break
        
        query_score = chunks_found / len(golden_contents)
        total_score += query_score
    
    average_score = total_score / total_queries
    pass_at_n = average_score * 100
    return {
        "pass_at_n": pass_at_n,
        "average_score": average_score,
        "total_queries": total_queries
    }

def manage_image_folder(folder: str):
    """Clear existing image folder and create a new one"""
    if os.path.exists(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)

def write_response_with_images(f, generated_response: str, extracted_images: List[Dict[str, Any]]):
    """Write the response and copy referenced images to a special folder"""
    # Create a folder for referenced images
    referenced_images_dir = "referenced_images"
    os.makedirs(referenced_images_dir, exist_ok=True)
    
    # Write the original response
    f.write("\nGenerated Response:\n")
    
    # Find all image references in the response
    referenced_files = []
    for img in extracted_images:
        if img['filename'] in generated_response:
            src_path = os.path.join("extracted_images", img['filename'])
            dest_path = os.path.join(referenced_images_dir, img['filename'])
            if os.path.exists(src_path):
                shutil.copy2(src_path, dest_path)
                referenced_files.append(img['filename'])
    
    # Add image references to the response
    modified_response = generated_response
    if referenced_files:
        modified_response += "\n\nReferenced Images:\n"
        for img_file in referenced_files:
            modified_response += f"\n- {img_file}"
            
    f.write(modified_response)

def main():
    parser = argparse.ArgumentParser(description="Process PDF files, create a vector database, and perform searches")
    parser.add_argument("-i", "--input", nargs="+", required=False, help="PDF files to process")
    parser.add_argument("-o", "--output", default="retrieval.txt", help="Output file for search results")
    parser.add_argument("-q", "--query", required=False, help="Search query")
    parser.add_argument("-k", "--top_k", type=int, default=20, help="Number of top results to return")
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
    
    # Use reranking for search
    search_results = base_db.search_with_rerank(search_query, k=args.top_k)

    # Perform RAG
    generated_response, used_images = perform_rag(search_query, search_results)

    # Clear and recreate image folder for new query
    manage_image_folder("extracted_images")
    
    # Write results to output file
    with open(args.output, "w") as f:
        f.write(f"Query: {search_query}\n\n")
        f.write("Search Results (with reranking):\n")
        
        # Track extracted images and their usage
        extracted_images = []
        
        for i, result in enumerate(search_results, 1):
            f.write(f"{i}. ")
            if result['metadata']['type'] == 'text':
                content = result['metadata']['content'][:500] + "..." \
                    if len(result['metadata']['content']) > 500 else result['metadata']['content']
                f.write(f"Text Content: {content}\n")
            elif result['metadata']['type'] == 'image':
                summary = result['metadata']['summary'][:500] + "..." \
                    if len(result['metadata']['summary']) > 500 else result['metadata']['summary']
                f.write(f"Image Summary: {summary}\n")
                
                image_path = result['metadata']['path']
                was_used = image_path in used_images
                
                extraction_result = extract_image(
                    image_path,
                    "extracted_images",
                    result['metadata'].get('model_used', 'Unknown')
                )
                
                extracted_images.append({
                    "filename": os.path.basename(extraction_result["path"]),
                    "model": extraction_result["model"],
                    "used_in_response": was_used
                })
                
                f.write(f"   Image extracted to: {extraction_result['path']}\n")
                f.write(f"   Used in response: {'Yes' if was_used else 'No'}\n")
            f.write(f"   Relevance Score: {result['similarity']:.4f}\n\n")
        
        # Write summary of extracted images
        if extracted_images:
            f.write("\nExtracted Images Summary:\n")
            f.write("-" * 40 + "\n")
            f.write("\nImages Used in Response:\n")
            for img in extracted_images:
                if img['used_in_response']:
                    f.write(f"✓ {img['filename']}\n")
            
            f.write("\nImages Not Used in Response:\n")
            for img in extracted_images:
                if not img['used_in_response']:
                    f.write(f"✗ {img['filename']}\n")
            
        # Write response with referenced images
        write_response_with_images(f, generated_response, extracted_images)

    print(f"Search results and generated response saved to {args.output}")

if __name__ == "__main__":
    main()
