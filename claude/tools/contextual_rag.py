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
import datetime

load_dotenv()

class ElasticsearchBM25:
    def __init__(self, index_name: str = "contextual_bm25_index"):
        print(f"\n[ElasticsearchBM25.__init__] Initializing with index: {index_name}")
        self.es_client = Elasticsearch("http://localhost:9200")
        self.index_name = index_name
        
        self.index_settings = {
            "settings": {
                "analysis": {"analyzer": {"default": {"type": "english"}}},
                "similarity": {"default": {"type": "BM25"}}
            },
            "mappings": {
                "properties": {
                    "text": {"type": "text", "analyzer": "english"},
                    "metadata": {"type": "keyword"}
                }
            }
        }
        self.create_index()

    def create_index(self):
        print(f"[ElasticsearchBM25.create_index] Checking if index exists: {self.index_name}")
        if not self.es_client.indices.exists(index=self.index_name):
            print(f"[ElasticsearchBM25.create_index] Creating new index: {self.index_name}")
            self.es_client.indices.create(index=self.index_name, body=self.index_settings)
        else:
            print(f"[ElasticsearchBM25.create_index] Index already exists: {self.index_name}")

    def index_documents(self, documents: List[Dict[str, Any]]):
        actions = []
        for doc in documents:
            actions.append({
                "_index": self.index_name,
                "_source": {
                    "text": f"{doc.get('content', '')} {doc.get('contextualized_content', '')}",
                    "metadata": json.dumps(doc)
                }
            })
        
        if actions:
            success, _ = bulk(self.es_client, actions)
            self.es_client.indices.refresh(index=self.index_name)
            return success
        return 0

    def search(self, query: str, k: int = 20) -> List[Dict[str, Any]]:
        search_body = {
            "query": {
                "match": {
                    "text": query
                }
            },
            "size": k
        }
        
        try:
            response = self.es_client.search(index=self.index_name, body=search_body)
            return [
                {
                    "content": json.loads(hit["_source"]["metadata"]),
                    "score": hit["_score"]
                }
                for hit in response["hits"]["hits"]
            ]
        except Exception as e:
            print(f"Search error: {e}")
            return []


class VectorDB:
    def __init__(self, name: str, api_key = None):
        print(f"\n[VectorDB.__init__] Initializing VectorDB with name: {name}")
        if api_key is None:
            api_key = os.getenv("VOYAGE_API_KEY")
        self.client = voyageai.Client(api_key=api_key)
        self.name = name
        self.embeddings = []
        self.metadata = []
        self.query_cache = {}
        self.db_path = f"../agent_db/{name}/vector_db.pkl"
        print(f"[VectorDB.__init__] Creating BM25 index: {name}_bm25_index")
        self.es_bm25 = ElasticsearchBM25(f"{name}_bm25_index")

    def load_data(self, dataset: List[Dict[str, Any]]):
        print("\nProcessing dataset:")
        print(f"   Total documents: {len(dataset)}")
        
        texts_to_embed = []
        metadata = []
        total_chunks = sum(len(doc['chunks']) for doc in dataset) + sum(len(doc.get('images', [])) for doc in dataset)
        
        print(f"   Total chunks to process: {total_chunks}")
        
        with tqdm(total=total_chunks, desc="Processing chunks and images") as pbar:
            for doc in dataset:
                # Process text chunks
                for chunk in doc['chunks']:
                    combined_text = f"""
Title: {chunk.get('document_title', '')}
Content: {chunk['content']}
Context: {chunk.get('context', '')}
"""
                    texts_to_embed.append(combined_text)
                    metadata.append({
                        'type': 'text',
                        'doc_id': doc['doc_id'],
                        'content': chunk['content'],
                        'context': chunk.get('context', ''),
                        'title': chunk.get('document_title', ''),
                        'combined_text': combined_text,
                    })
                    pbar.update(1)
                
                # Process images
                for image in doc.get('images', []):
                    print(f"\n   Processing image: {image['path']}")
                    combined_text = f"""
Title: {image.get('document_title', '')}
Content: {image.get('content', '')}
Context: {image.get('context', '')}
"""
                    texts_to_embed.append(combined_text)
                    metadata.append({
                        'type': 'image',
                        'doc_id': doc['doc_id'],
                        'path': image['path'],
                        'content': image.get('content', ''),
                        'context': image.get('context', ''),
                        'title': image.get('document_title', ''),
                        'combined_text': combined_text,
                    })
                    pbar.update(1)

        # Embed and store data
        self._embed_and_store(texts_to_embed, metadata)
        
        # Index documents in Elasticsearch
        documents = [
            {
                'content': item['content'],
                'contextualized_content': item['combined_text'],
                'original_index': i,
            }
            for i, item in enumerate(metadata)
        ]
        
        self.es_bm25.index_documents(documents)
        self.save_db()
        
        print(f"Vector database loaded and saved. Total items processed: {len(texts_to_embed)}")
        print(f"Text chunks: {len([m for m in metadata if m['type'] == 'text'])}")
        print(f"Images: {len([m for m in metadata if m['type'] == 'image'])}")

    def _embed_and_store(self, texts: List[str], data: List[Dict[str, Any]]):
        print(f"\n[VectorDB._embed_and_store] Embedding {len(texts)} texts")
        batch_size = 128
        with tqdm(total=len(texts), desc="Embedding items") as pbar:
            result = []
            for i in range(0, len(texts), batch_size):
                print(f"[VectorDB._embed_and_store] Processing batch {i//batch_size + 1}")
                batch = texts[i : i + batch_size]
                batch_result = self.client.embed(batch, model="voyage-2").embeddings
                result.extend(batch_result)
                pbar.update(len(batch))
        
        print("[VectorDB._embed_and_store] Storing embeddings and metadata")
        self.embeddings = result
        self.metadata = data

    def search(self, query: str, k: int = 20) -> List[Dict[str, Any]]:
        print(f"\n[VectorDB.search] Searching for: {query}")
        if query in self.query_cache:
            print("[VectorDB.search] Using cached query embedding")
            query_embedding = self.query_cache[query]
        else:
            print("[VectorDB.search] Computing new query embedding")
            query_embedding = self.client.embed([query], model="voyage-2").embeddings[0]
            self.query_cache[query] = query_embedding

        print("[VectorDB.search] Computing similarities")
        similarities = np.dot(self.embeddings, query_embedding) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        top_k_indices = np.argsort(similarities)[-k:][::-1]
        print(f"[VectorDB.search] Found {k} top results")
        
        return [
            {
                'metadata': {
                    **self.metadata[idx],  # Include all metadata fields
                    'original_content': self.metadata[idx].get('content', ''),  # Keep original content
                    'original_context': self.metadata[idx].get('context', ''),  # Keep original context
                    'original_title': self.metadata[idx].get('title', '')  # Keep original title
                },
                'similarity': float(similarities[idx])
            }
            for idx in top_k_indices
        ]

    def hybrid_search(self, query: str, k: int = 20) -> List[Dict[str, Any]]:
        print("\nPerforming hybrid search:")
        print("1. Getting semantic search results...")
        semantic_results = self.search(query, k=k)
        
        print("\n2. Getting BM25 search results...")
        bm25_results = self.es_bm25.search(query, k=k)
        
        # Add detailed BM25 results printing
        print("\nBM25 Search Results:")
        for i, result in enumerate(bm25_results, 1):
            print(f"\nResult {i}:")
            print(f"Score: {result['score']:.4f}")
            print(f"Content: {result['content'].get('content', '')[:200]}...")  # Print first 200 chars
            print(f"Metadata: {json.dumps(result['content'], indent=2)}")  # Print full metadata
            print("-" * 80)
        
        print("\n3. Combining results...")
        combined_results = []
        for sem_result in semantic_results:
            matching_bm25 = next(
                (b for b in bm25_results if b['content'].get('content', '') == sem_result['metadata'].get('original_content', '')), 
                None
            )
            
            if matching_bm25:
                combined_score = (sem_result['similarity'] + matching_bm25['score']) / 2
                print(f"   Combined score: {combined_score:.4f} (semantic: {sem_result['similarity']:.4f}, BM25: {matching_bm25['score']:.4f})")
            else:
                combined_score = sem_result['similarity']
                print(f"   Using semantic score only: {combined_score:.4f}")
                
            combined_results.append({
                'metadata': sem_result['metadata'],
                'similarity': combined_score
            })
            
        return sorted(combined_results, key=lambda x: x['similarity'], reverse=True)[:k]

    def save_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "wb") as file:
            pickle.dump({
                "embeddings": self.embeddings,
                "metadata": self.metadata,
                "query_cache": self.query_cache,
            }, file)

    def load_db(self):
        if not os.path.exists(self.db_path):
            raise ValueError("Vector database file not found. Use load_data to create a new database.")
        with open(self.db_path, "rb") as file:
            data = pickle.load(file)
        self.embeddings = data["embeddings"]
        self.metadata = data["metadata"]
        self.query_cache = data["query_cache"]
        print(f"Loaded database with {len(self.metadata)} items")
        print(f"Text chunks: {len([m for m in self.metadata if m['type'] == 'text'])}")
        print(f"Images: {len([m for m in self.metadata if m['type'] == 'image'])}")

def process_pdfs(pdf_files: List[str]) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf2json_path = os.path.join(current_dir, "pdf2json_chunked.py")
    
    cmd = [sys.executable, pdf2json_path] + pdf_files + ["-o", "../agent_db/data/data.json"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running pdf2json.py: {e}")
        sys.exit(1)
    
    return "../agent_db/data/data.json"

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
    print("\n[perform_rag] Starting RAG process")
    
    # Add this prompt template definition
    prompt = ChatPromptTemplate.from_template("""
    Answer the following question using only the provided context. If you cannot answer the question based on the context, say "I cannot answer this based on the provided context."

    Context:
    {context}

    Question:
    {query}
    """)
    
    context = ""
    used_images = []
    
    print("[perform_rag] Building context from search results...")
    for i, result in enumerate(search_results):
        try:
            metadata = result['metadata']
            print(f"\n[perform_rag] Processing result {i+1}:")
            print(f"   Type: {metadata.get('type')}")
            print(f"   Similarity: {result.get('similarity', 0):.4f}")
            
            if metadata.get('type') == 'text':
                print(f"   Adding text content (length: {len(metadata.get('content', ''))})")
                context += f"Text: {metadata.get('content', '')}\n\n"
            elif metadata.get('type') == 'image':
                image_path = metadata.get('path', '')
                if image_path:
                    used_images.append(image_path)
                    print(f"   Added image: {image_path}")
                context += f"Image Summary: {metadata.get('summary', '')}\n\n"
            
        except Exception as e:
            print(f"[perform_rag] Error processing result: {e}")
            continue

    print("\n[perform_rag] Generating response using LLM...")
    model = ChatOpenAI(temperature=0, model="gpt-4")
    chain = prompt | model | StrOutputParser()
    response = chain.invoke({"context": context, "query": search_query})
    
    print(f"[perform_rag] Generated response (length: {len(response)})")
    print(f"[perform_rag] Used {len(used_images)} images")
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
    referenced_images_dir = "../agent_db/results/extracted_images"
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


def save_results(results: List[Dict], query: str, output_file: str) -> str:
    print(f"\n[save_results] Saving results for query: {query}")
    output_data = {
        "query": query,
        "timestamp": datetime.datetime.now().isoformat(),
        "results": []
    }
    
    print("[save_results] Processing results...")
    for i, result in enumerate(results, 1):
        metadata = result['metadata']
        print(f"[save_results] Processing result {i}")
        result_entry = {
            "rank": i,
            "similarity_score": float(result['similarity']),
            "type": metadata['type']
        }
        
        if metadata['type'] == 'text':
            print(f"[save_results] Adding text content (length: {len(metadata['content'])})")
        else:  # image
            print(f"[save_results] Adding image: {metadata['path']}")
            
        output_data["results"].append(result_entry)
    
    output_path = f"../agent_db/results/{output_file}"
    print(f"[save_results] Saving to: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return output_path

def create_elasticsearch_bm25_index(db: VectorDB):
    es_bm25 = ElasticsearchBM25()
    
    documents = []
    for i, item in enumerate(db.metadata):
        doc = {
            'content': item.get('content', ''),
            'contextualized_content': item.get('combined_text', ''),
            'type': item.get('type', ''),
            'original_index': i
        }
        documents.append(doc)
    
    es_bm25.index_documents(documents)
    return es_bm25

def write_results(query: str, results: List[Dict[str, Any]], output_file: str = "../agent_db/results/retrieval.txt"):
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Query: {query}\n\n")
        f.write("Search Results (with reranking):\n")
        for i, result in enumerate(results, 1):
            f.write(f"{i}. Metadata:\n")
            # Write all metadata fields
            for key, value in result['metadata'].items():
                if isinstance(value, (str, int, float)):
                    f.write(f"   {key}: {value}\n")
                elif isinstance(value, dict):
                    f.write(f"   {key}:\n")
                    for sub_key, sub_value in value.items():
                        f.write(f"      {sub_key}: {sub_value}\n")
                elif isinstance(value, list):
                    f.write(f"   {key}: {', '.join(map(str, value))}\n")
            
            # Write similarity score
            f.write(f"   Relevance Score: {result['similarity']:.4f}\n\n")

def main():
    parser = argparse.ArgumentParser(description="Process PDF files, create a vector database, and perform searches")
    parser.add_argument("-i", "--input", nargs="+", required=False, help="PDF files to process")
    parser.add_argument("-o", "--output", default="../agent_db/results/retrieval.txt", help="Output file for search results")
    parser.add_argument("-q", "--query", required=False, help="Search query")
    parser.add_argument("-k", "--top_k", type=int, default=10, help="Number of top results to return")
    args = parser.parse_args()

    print("\n1. Initializing Vector Database...")
    base_db = VectorDB("base_db")

    if args.input:
        print("\n2. Processing input files...")
        # json_file = process_pdfs(args.input)
        json_file = "../agent_db/documents.json"
        print(f"   Loading data from: {json_file}")
        
        with open(json_file, 'r') as f:
            transformed_dataset = json.load(f)
        print(f"   Dataset loaded with {len(transformed_dataset)} documents")

        print("\n3. Creating new vector database...")
        base_db.load_data(transformed_dataset)
    else:
        try:
            print("\n2. Loading existing vector database...")
            base_db.load_db()
        except ValueError as e:
            print(f"Error: {e}")
            print("Please provide input PDFs to create a new database.")
            sys.exit(1)

    if args.query:
        search_query = args.query
    else:
        search_query = input("\n4. Enter your search query: ")

    print(f"\n5. Searching for: {search_query}")
    
    print("\n6. Creating BM25 index...")
    es_bm25 = create_elasticsearch_bm25_index(base_db)

    print("\n7. Performing hybrid search...")
    search_results = base_db.hybrid_search(search_query, k=args.top_k)
    print(f"   Found {len(search_results)} results")

    print("\n8. Performing RAG...")
    generated_response, used_images = perform_rag(search_query, search_results)
    print(f"   Generated response with {len(used_images)} referenced images")

    print("\n9. Managing image folder...")
    manage_image_folder("../agent_db/results/extracted_images")
    
    # Write results to output file
    with open(args.output, "w") as f:
        f.write(f"Query: {search_query}\n\n")
        f.write("Search Results (with reranking):\n")
        
        # Track extracted images and their usage
        extracted_images = []
        
        for i, result in enumerate(search_results, 1):
            f.write(f"{i}. ")
            if result['metadata']['type'] == 'text':
                f.write(f"{result['metadata']}\n")
            elif result['metadata']['type'] == 'image':
                f.write(f"{result['metadata']}\n")
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