import os
import pickle
import json
import numpy as np
import voyageai
from typing import List, Dict, Any, Optional, Tuple
from tqdm import tqdm
from dotenv import load_dotenv
import argparse
import sys
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import datetime

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

class VectorDB:
    def __init__(self, name: str, api_key = None):
        if api_key is None:
            api_key = os.getenv("VOYAGE_API_KEY")
        self.client = voyageai.Client(api_key=api_key)
        self.name = name
        self.embeddings = []
        self.metadata = []
        self.query_cache = {}
        self.db_path = f"../agent_db/{name}/vector_db.pkl"
        self.es_bm25 = ElasticsearchBM25(f"{name}_bm25_index")

    def load_data(self, dataset: List[Dict[str, Any]]):
        texts_to_embed = []
        metadata = []
        
        with tqdm(total=len(dataset), desc="Processing items") as pbar:
            for item in dataset:
                texts_to_embed.append(item['content'])
                metadata.append(item['metadata'])
                pbar.update(1)

        self._embed_and_store(texts_to_embed, metadata)
        
        documents = []
        for item in dataset:
            if item['metadata']['type'] == 'text':
                documents.append({
                    'original_content': item['metadata']['content'],
                    'contextualized_content': item['metadata']['combined_text'],
                    'doc_id': item['id'],
                    'chunk_id': item['id'],
                    'original_index': metadata.index(item['metadata'])
                })
        
        self.es_bm25.index_documents(documents)
        self.save_db()
        
        print(f"Database loaded with {len(texts_to_embed)} items")
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
            raise ValueError("No embeddings found. Please load data first.")

        similarities = np.dot(self.embeddings, query_embedding) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        
        top_k_indices = np.argsort(similarities)[-k:][::-1]
        
        results = []
        for idx in top_k_indices:
            results.append({
                'metadata': self.metadata[idx],
                'similarity': float(similarities[idx])
            })
        
        return results

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
            raise ValueError("No database found. Use load_data to create a new database.")
        with open(self.db_path, "rb") as file:
            data = pickle.load(file)
        self.embeddings = data["embeddings"]
        self.metadata = data["metadata"]
        self.query_cache = json.loads(data["query_cache"])
        print(f"Loaded database with {len(self.metadata)} items")
        print(f"Text chunks: {len([m for m in self.metadata if m['type'] == 'text'])}")
        print(f"Images: {len([m for m in self.metadata if m['type'] == 'image'])}")

def transform_documents_to_db_format(json_file: str) -> List[Dict[str, Any]]:
    with open(json_file, 'r') as f:
        documents = json.load(f)
    
    transformed_data = []
    
    for doc in documents:
        for chunk in doc['chunks']:
            combined_text = f"""
Content: {chunk['content']}
Context: {chunk['context']}
"""
            transformed_data.append({
                'id': chunk['chunk_id'],
                'type': 'text',
                'content': combined_text,
                'metadata': {
                    'type': 'text',
                    'content': chunk['content'],
                    'context': chunk['context'],
                    'document_title': chunk['document_title'],
                    'is_table': chunk['is_table'],
                    'table_type': chunk['table_type'],
                    'original_content': chunk['content'],
                    'combined_text': combined_text
                }
            })
        
        if 'images' in doc:
            for image in doc['images']:
                combined_text = f"""
Image Path: {image['path']}
Image Context: {image.get('context', '')}
"""
                transformed_data.append({
                    'id': image['image_id'],
                    'type': 'image',
                    'content': combined_text,
                    'metadata': {
                        'type': 'image',
                        'path': image['path'],
                        'summary': image.get('context', ''),
                        'document_title': image.get('document_title', ''),
                        'is_table': image.get('is_table', False),
                        'table_type': image.get('table_type', None),
                        'model_used': image.get('model_used', 'Unknown'),
                        'combined_text': combined_text
                    }
                })
    
    return transformed_data

def save_results(results: List[Dict[str, Any]], query: str, output_file: str):
    """Save search results to a JSON file"""
    output_data = {
        "query": query,
        "timestamp": datetime.datetime.now().isoformat(),
        "results": []
    }
    
    for i, result in enumerate(results, 1):
        metadata = result['metadata']
        result_entry = {
            "rank": i,
            "similarity_score": float(result['similarity']),
            "type": metadata['type']
        }
        
        if metadata['type'] == 'text':
            result_entry.update({
                "content": metadata['content'],
                "context": metadata['context'],
                "document_title": metadata.get('document_title', ''),
                "is_table": metadata.get('is_table', False),
                "table_type": metadata.get('table_type', None)
            })
        else:  # image
            result_entry.update({
                "image_path": metadata['path'],
                "image_context": metadata.get('summary', ''),
                "document_title": metadata.get('document_title', ''),
                "is_table": metadata.get('is_table', False),
                "table_type": metadata.get('table_type', None)
            })
            
        output_data["results"].append(result_entry)
    
    # Create results directory if it doesn't exist
    os.makedirs("../agent_db/results", exist_ok=True)
    
    # Save to file
    output_path = f"../agent_db/results/{output_file}"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return output_path

def extract_tables_from_paper(documents: List[Dict[str, Any]], paper_title: str) -> List[Dict[str, Any]]:
    """
    Extract all tables (both text-based and image-based) from a specific paper
    Returns only items where is_table is True
    """
    tables = []
    
    for doc in documents:
        if doc['title'].lower() == paper_title.lower():
            # Extract text-based tables from chunks
            for chunk in doc['chunks']:
                if chunk.get('is_table') is True:  # Explicitly check for True
                    tables.append({
                        'type': 'text_table',
                        'content': chunk['content'],
                        'context': chunk['context'],
                        'table_type': chunk.get('table_type', 'text_based'),
                        'document_title': chunk['document_title']
                    })
            
            # Extract image-based tables
            if 'images' in doc:
                for image in doc['images']:
                    if image.get('is_table') is True:  # Explicitly check for True
                        tables.append({
                            'type': 'image_table',
                            'path': image['path'],
                            'context': image.get('context', ''),
                            'table_type': image.get('table_type', 'image_based'),
                            'document_title': image.get('document_title', '')
                        })
    
    if not tables:
        print(f"No tables (is_table: true) found in paper: {paper_title}")
    else:
        print(f"Found {len(tables)} tables (is_table: true) in paper: {paper_title}")
    
    return tables

def save_table_results(tables: List[Dict[str, Any]], paper_title: str, output_file: str) -> str:
    """Save extracted tables to a JSON file"""
    output_data = {
        "paper_title": paper_title,
        "timestamp": datetime.datetime.now().isoformat(),
        "total_tables": len(tables),
        "tables": []
    }
    
    for i, table in enumerate(tables, 1):
        table_entry = {
            "table_number": i,
            "type": table['type'],
            "table_type": table['table_type']
        }
        
        if table['type'] == 'text_table':
            table_entry.update({
                "content": table['content'],
                "context": table['context']
            })
        else:  # image_table
            table_entry.update({
                "image_path": table['path'],
                "context": table['context']
            })
            
        output_data["tables"].append(table_entry)
    
    # Create results directory if it doesn't exist
    os.makedirs("../agent_db/results", exist_ok=True)
    
    # Save to file
    output_path = f"../agent_db/results/{output_file}"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Search vector database or extract tables from papers")
    parser.add_argument("-i", "--input", required=False, help="Input JSON file path")
    parser.add_argument("-q", "--query", required=False, help="Search query")
    parser.add_argument("-k", "--top_k", type=int, default=5, help="Number of results to return")
    parser.add_argument("-o", "--output", default="search_results.json", help="Output file name for results")
    parser.add_argument("-t", "--tables", required=False, help="Extract tables from paper with given title")
    args = parser.parse_args()

    if args.tables:
        # Load documents directly for table extraction
        try:
            with open('../agent_db/documents.json', 'r') as f:
                documents = json.load(f)
            
            tables = extract_tables_from_paper(documents, args.tables)
            
            if not tables:
                print(f"No tables found in paper: {args.tables}")
                return
            
            # Save and display results
            output_file = f"tables_{args.tables.lower().replace(' ', '_')}.json"
            output_path = save_table_results(tables, args.tables, output_file)
            
            print(f"\nFound {len(tables)} tables in paper: {args.tables}")
            print(f"Results saved to: {output_path}\n")
            
            # Display table information
            for i, table in enumerate(tables, 1):
                print(f"\nTable {i}:")
                print(f"Type: {table['type']}")
                print(f"Table Type: {table['table_type']}")
                
                if table['type'] == 'text_table':
                    print("Content:")
                    print("-" * 40)
                    print(table['content'][:200] + "..." if len(table['content']) > 200 else table['content'])
                    print("-" * 40)
                    print(f"Context: {table['context']}")
                else:
                    print(f"Image Path: {table['path']}")
                    print(f"Context: {table['context']}")
                print("-" * 80)
            
            return tables
            
        except FileNotFoundError:
            print("Error: documents.json not found")
            return
        except json.JSONDecodeError:
            print("Error: Invalid JSON format in documents.json")
            return
        except Exception as e:
            print(f"Error: {e}")
            return

    # Existing search functionality
    base_db = VectorDB("base_db")
    try:
        base_db.load_db()
        print("Loaded existing database")
    except ValueError:
        if args.input:
            print("Creating new database")
            transformed_dataset = transform_documents_to_db_format(args.input)
            base_db.load_data(transformed_dataset)
        else:
            print("No existing database found and no input file provided")
            sys.exit(1)

    if args.query:
        results = base_db.search(args.query, k=args.top_k)
        output_path = save_results(results, args.query, args.output)
        print(f"\nResults saved to: {output_path}")
        
        print(f"\nTop {args.top_k} results for query: {args.query}\n")
        for i, result in enumerate(results, 1):
            metadata = result['metadata']
            print(f"\nResult {i} (Score: {result['similarity']:.4f}):")
            print(f"Type: {metadata['type']}")
            if metadata['type'] == 'text':
                print(f"Content: {metadata['content'][:200]}...")
                print(f"Context: {metadata['context']}")
            else:
                print(f"Image Path: {metadata['path']}")
                print(f"Image Context: {metadata['summary']}")
            print("-" * 80)
        
        return results

if __name__ == "__main__":
    results = main()
