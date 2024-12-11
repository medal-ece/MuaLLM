import os
import pickle
import json
import numpy as np
import voyageai
from typing import List, Dict, Any
from tqdm import tqdm
import dotenv
import anthropic
import threading
import time
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
from tenacity import retry, stop_after_attempt, wait_exponential
import cohere

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

dotenv.load_dotenv()

client = anthropic.Client()

class ContextualVectorDB:
    def __init__(self, name: str, voyage_api_key=None, claude_api_key=None):
        if voyage_api_key is None:
            voyage_api_key = os.getenv("VOYAGE_API_KEY")
        if claude_api_key is None:
            claude_api_key = os.getenv("CLAUDE_API_KEY")
        self.voyage_client = voyageai.Client()
        self.anthropic_client = anthropic.Client()
        self.name = name
        self.embeddings=[]
        self.metadata=[]
        self.query_cache={}
        self.db_path= f"/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/base_db/vector_db.pkl"
        self.token_counts={
            'input': 0,
            'output': 0,
            "cache_read": 0,
            "cache_creation": 0,
        }
        self.token_lock=threading.Lock()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def situate_text_context(self,doc:str, chunk:str) -> tuple[str, Any]:

        DOCUMENT_CONTEXT_PROMPT = """
        <document>
        {doc_content}
        </document>
        """

        CHUNK_CONTEXT_PROMPT = """
        Here is the chunk we want to situate within the whole document
        <chunk>
        {chunk_content}
        </chunk>
        Start with this text is from the document title  Example: "This text is from the document 1.2-V Supply, 100-nW, 1.09-V Bandgap and 0.7-V Supply, 52.5-nW, 0.55-V Subbandgap Reference Circuits for Nanowatt CMOS LSIs"
        Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk.
        Answer only with the succinct context , mention the title of the document and nothing else.
        """
        try:
            response = self.anthropic_client.beta.prompt_caching.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1000,
                temperature=0.0,
                messages=[
                    {
                        "role": "user", 
                        "content": [
                            {
                                "type": "text",
                                "text": DOCUMENT_CONTEXT_PROMPT.format(doc_content=doc),
                                "cache_control": {"type": "ephemeral"} #we will make use of prompt caching for the full documents
                            },
                            {
                                "type": "text",
                                "text": CHUNK_CONTEXT_PROMPT.format(chunk_content=chunk),
                            },
                        ]
                    },
                ],
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
            )
               
            return response.content[0].text, response.usage
        except anthropic.RateLimitError:
            print("Rate limit hit, waiting 60 seconds...")
            time.sleep(60)
            raise  # This will trigger the retry
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def situate_image_context(self, doc: str,path: str, base64_image: str) -> tuple[str, Any]:
        DOCUMENT_CONTEXT_PROMPT = """
        <document>
        {doc_content}
        </document>
        """

        IMAGE_CONTEXT_PROMPT = """
        Please provide a detailed description of this image that would help in search retrieval. Your description should:
        1. Start with this image is from the document title  Example: "This image is from the document 1.2-V Supply, 100-nW, 1.09-V Bandgap and 0.7-V Supply, 52.5-nW, 0.55-V Subbandgap Reference Circuits for Nanowatt CMOS LSIs"
        2. Mention the type of image (e.g., "Schematic diagram", "Circuit diagram", "Graph", "Plot", "Illustration")
        3. Describe the key visual elements and their relationships
        4. Mention any text, labels, or annotations visible in the image
        5. Note any technical components or symbols if present
        6. Explain what concept or system this image is depicting
        
        
        Format your response as a clear, detailed paragraph that would help someone find this image when searching.
        Focus on being specific and technical rather than general.
        """

        try:
            response = self.anthropic_client.beta.prompt_caching.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1000,
                temperature=0.0,
                messages=[
                    {
                        "role": "user", 
                        "content": [
                            {
                                "type": "text",
                                "text": DOCUMENT_CONTEXT_PROMPT.format(doc_content=doc),
                                "cache_control": {"type": "ephemeral"}
                            },
                            {
                                "type": "image", 
                                "source": {"type": "base64", "media_type": "image/jpeg", "data": base64_image}
                            },
                            {
                                "type": "text", 
                                "text": IMAGE_CONTEXT_PROMPT
                            }
                        ]
                    },
                ],
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
            )
            
            context = response.content[0].text
            
            return context, response.usage
            
        except anthropic.RateLimitError:
            print("Rate limit hit, waiting 60 seconds...")
            time.sleep(60)
            raise  # This will trigger the retry
    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def load_data(self, dataset: List[Dict[str, Any]], parallel_threads: int = 1):
        texts_to_embed = []
        metadata = []
        
        # Process in smaller batches
        BATCH_SIZE = 5  # Process 5 items at a time
        
        def process_batch(items_to_process):
            local_texts = []
            local_metadata = []
            
            for item in items_to_process:
                try:
                    if 'content' in item[1]:  # It's a chunk
                        doc, chunk = item
                        time.sleep(3)  # Longer delay between requests
                        contextualized_text, usage = self.situate_text_context(doc["content"], chunk["content"])
                        with self.token_lock:
                            self.token_counts['input'] += usage.input_tokens
                            self.token_counts['cache_read'] += usage.cache_read_input_tokens
                            self.token_counts['cache_creation'] += usage.cache_creation_input_tokens
                        
                        result = {
                            'text_to_embed': f"{chunk['content']}\n\n{contextualized_text}",
                            'metadata': {
                                'doc_id': doc['doc_id'],
                                'original_uuid': doc['original_uuid'],
                                'chunk_id': chunk['chunk_id'],
                                'original_index': chunk['original_index'],
                                'original_content': chunk['content'],
                                'contextualized_content': contextualized_text
                            }
                        }
                    else:  # It's an image
                        doc, image = item
                        time.sleep(3)  # Longer delay between requests
                        base64_image = self.encode_image(image["path"])
                        contextualized_text, usage = self.situate_image_context(doc["content"],image["path"], base64_image)
                        with self.token_lock:
                            self.token_counts['input'] += usage.input_tokens
                            self.token_counts['cache_read'] += usage.cache_read_input_tokens
                            self.token_counts['cache_creation'] += usage.cache_creation_input_tokens
                        
                        result = {
                            'text_to_embed': contextualized_text,
                            'metadata': {
                                'doc_id': doc['doc_id'],
                                'image_id': image['image_id'],
                                'path': image['path'],
                                "contextualized_content": contextualized_text
                            }
                        }
                    
                    local_texts.append(result['text_to_embed'])
                    local_metadata.append(result['metadata'])
                    
                except Exception as e:
                    print(f"Error processing item: {e}")
                    time.sleep(60)  # Wait longer on error
                    continue
                
            return local_texts, local_metadata

        # Prepare all items to process
        all_items = []
        for doc in dataset:
            for chunk in doc["chunks"]:
                all_items.append((doc, chunk))
            for image in doc["images"]:
                all_items.append((doc, image))

        print(f"Total items to process: {len(all_items)}")
        
        # Process in batches
        for i in range(0, len(all_items), BATCH_SIZE):
            batch = all_items[i:i + BATCH_SIZE]
            print(f"\nProcessing batch {i//BATCH_SIZE + 1}/{(len(all_items) + BATCH_SIZE - 1)//BATCH_SIZE}")
            
            batch_texts, batch_metadata = process_batch(batch)
            texts_to_embed.extend(batch_texts)
            metadata.extend(batch_metadata)
            
            # Add a longer delay between batches
            if i + BATCH_SIZE < len(all_items):
                print("Waiting between batches...")
                time.sleep(30)  # 30 second delay between batches
            
            # Save progress after each batch
            self._embed_and_store(texts_to_embed, metadata)
            self.save_db()
            print(f"Progress: {len(texts_to_embed)}/{len(all_items)} items processed")

        # Final save
        self._embed_and_store(texts_to_embed, metadata)
        self.save_db()

        # Print statistics
        print(f"\nContextual Vector database loaded and saved. Total items processed: {len(texts_to_embed)}")
        print(f"Total input tokens without caching: {self.token_counts['input']}")
        print(f"Total output tokens: {self.token_counts['output']}")
        print(f"Total input tokens written to cache: {self.token_counts['cache_creation']}")
        print(f"Total input tokens read from cache: {self.token_counts['cache_read']}")
        
        total_tokens = self.token_counts['input'] + self.token_counts['cache_read'] + self.token_counts['cache_creation']
        savings_percentage = (self.token_counts['cache_read'] / total_tokens) * 100 if total_tokens > 0 else 0
        print(f"Total input token savings from prompt caching: {savings_percentage:.2f}%")

    def _embed_and_store(self, texts: List[str], data: List[Dict[str, Any]]):
        batch_size = 128
        result = [
            self.voyage_client.embed(
                texts[i : i + batch_size],
                model="voyage-2"
            ).embeddings
            for i in range(0, len(texts), batch_size)
        ]
        self.embeddings = [embedding for batch in result for embedding in batch]
        self.metadata = data

    def save_db(self):
        data={
            "embeddings": self.embeddings,
            "metadata": self.metadata,
            "query_cache": json.dumps(self.query_cache),
        }
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "wb") as f:
            pickle.dump(data, f)

    def load_db(self):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Vector database file not found: {self.db_path}")
        with open(self.db_path, "rb") as f:
            data=pickle.load(f)
        self.embeddings=data["embeddings"]
        self.metadata=data["metadata"]
        self.query_cache=json.loads(data["query_cache"])
    
    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        if query in self.query_cache:
            query_embedding = self.query_cache[query]
        else:
            query_embedding = self.voyage_client.embed(query, model="voyage-2").embeddings[0]
            self.query_cache[query] = query_embedding
        if not self.embeddings:
            raise ValueError("Vector database is empty. Please load or embed data first.")
        
        similarities = np.dot(self.embeddings, query_embedding)
        top_indices=np.argsort(similarities)[::-1][:top_k]
        top_results=[]
        for index in top_indices:
            result={
                "metadata": self.metadata[index],
                "similarity": float(similarities[index]),
            }
            top_results.append(result)
        return top_results
    
class ElasticSearchBM25:
    def __init__(self, name:str= "contextual_bm25_index"):
        self.es_client = Elasticsearch("http://localhost:9200")
        self.index_name = name
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
                    "image_id": {"type": "keyword", "index": False},
                    "original_index": {"type": "integer", "index": False},
                    "content_type": {"type": "keyword"},  # 'text' or 'image'
                    "image_path": {"type": "keyword", "index": False}
                }
            }
        }
        if not self.es_client.indices.exists(index=self.index_name):
            self.es_client.indices.create(index=self.index_name, body=index_settings)
            print(f"Created index: {self.index_name}")
    def index_documents(self, documents: List[Dict[str, Any]]):
        actions = []
        image_count = 0
        text_count = 0
        
        for doc in documents:
            # Determine if this is an image or text chunk based on metadata
            is_image = 'image_id' in doc
            
            if is_image:
                image_count += 1
            else:
                text_count += 1
                
            action = {
                "_index": self.index_name,
                "_source": {
                    "contextualized_content": doc["contextualized_content"],
                    "doc_id": doc["doc_id"],
                    "content_type": "image" if is_image else "text"
                }
            }
            
            if is_image:
                action["_source"].update({
                    "image_id": doc["image_id"],
                    "image_path": doc["path"]
                })
            else:
                action["_source"].update({
                    "content": doc["original_content"],
                    "chunk_id": doc["chunk_id"],
                    "original_index": doc["original_index"]
                })
                
            actions.append(action)

        # print(f"\n=== Indexing Statistics ===")
        # print(f"Total documents: {len(documents)}")
        # print(f"Images: {image_count}")
        # print(f"Texts: {text_count}")

        success, _ = bulk(self.es_client, actions)
        self.es_client.indices.refresh(index=self.index_name)
        return success
    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        self.es_client.indices.refresh(index=self.index_name)  # Force refresh before each search
        search_body = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["content", "contextualized_content"],
                                "type": "best_fields"
                            }
                        },
                        {
                            "match": {
                                "contextualized_content": {
                                    "query": query,
                                    "boost": 1.0
                                }
                            }
                        }
                    ]
                }
            },
            "size": top_k,
        }
        response = self.es_client.search(index=self.index_name, body=search_body)
        
        results = []
        for hit in response["hits"]["hits"]:
            result = {
                "doc_id": hit["_source"]["doc_id"],
                "contextualized_content": hit["_source"]["contextualized_content"],
                "score": hit["_score"],
            }
            
            # Add fields specific to content type
            if hit["_source"]["content_type"] == "text":
                result.update({
                    "original_index": hit["_source"]["original_index"],
                    "content": hit["_source"]["content"],
                })
            else:  # image type
                result.update({
                    "image_id": hit["_source"]["image_id"],
                    "image_path": hit["_source"]["image_path"],
                })
                
            results.append(result)
        
        return results
def create_elasticsearch_bm25_index(db: ContextualVectorDB):
    es_bm25 = ElasticSearchBM25()
    es_bm25.index_documents(db.metadata)
    return es_bm25

def chunk_to_content(result: Dict[str, Any]) -> str:
    # Check if it's an image or text result
    if 'image_id' in result['item']:
        # For images, we only have contextualized content
        return result['item']['contextualized_content']
    else:
        # For text chunks, we combine original and contextualized content
        original_content = result['item']['original_content']
        contextualized_content = result['item']['contextualized_content']
        return f"{original_content}\n\nContext: {contextualized_content}"

def retrieve_advanced(query: str, db: ContextualVectorDB, es_bm25: ElasticSearchBM25, k: int, semantic_weight: float = 0.8, bm25_weight: float = 0.2):
    num_chunks_to_recall = 150

    # Semantic search
    semantic_results = db.search(query, top_k=num_chunks_to_recall)
    ranked_ids = []
    for result in semantic_results:
        metadata = result['metadata']
        if 'image_id' in metadata:
            ranked_ids.append(('image', metadata['doc_id'], metadata['image_id']))
        else:
            ranked_ids.append(('text', metadata['doc_id'], metadata['original_index']))

    # BM25 search using Elasticsearch
    bm25_results = es_bm25.search(query, top_k=num_chunks_to_recall)
    ranked_bm25_ids = []
    for result in bm25_results:
        if 'content' in result:  # Text chunk
            ranked_bm25_ids.append(('text', result['doc_id'], result['original_index']))
        else:  # Image
            ranked_bm25_ids.append(('image', result['doc_id'], result['image_id']))

    # Combine results
    item_ids = list(set(ranked_ids + ranked_bm25_ids))
    item_id_to_score = {}

    # Initial scoring with weights
    for item_id in item_ids:
        score = 0
        if item_id in ranked_ids:
            index = ranked_ids.index(item_id)
            score += semantic_weight * (1 / (index + 1))
        if item_id in ranked_bm25_ids:
            index = ranked_bm25_ids.index(item_id)
            score += bm25_weight * (1 / (index + 1))
        item_id_to_score[item_id] = score

    # Sort IDs by their scores
    sorted_ids = sorted(
        item_id_to_score.keys(), 
        key=lambda x: (item_id_to_score[x], x[1], x[2]), 
        reverse=True
    )

    # Assign new scores based on sorted order
    for index, item_id in enumerate(sorted_ids):
        item_id_to_score[item_id] = 1 / (index + 1)

    # Prepare final results
    final_results = []
    semantic_count = 0
    bm25_count = 0
    
    for item_id in sorted_ids[:k]:
        content_type, doc_id, sub_id = item_id
        
        try:
            # Find matching metadata
            if content_type == 'text':
                item_metadata = next(
                    (item for item in db.metadata 
                    if 'chunk_id' in item 
                    and item['doc_id'] == doc_id 
                    and item['original_index'] == sub_id),
                    None
                )
            else:  # image
                item_metadata = next(
                    (item for item in db.metadata 
                    if 'image_id' in item 
                    and item['doc_id'] == doc_id 
                    and item['image_id'] == sub_id),
                    None
                )

            # Skip if metadata not found
            if item_metadata is None:
                continue

            is_from_semantic = item_id in ranked_ids
            is_from_bm25 = item_id in ranked_bm25_ids
            
            final_results.append({
                'item': item_metadata,
                'content_type': content_type,
                'score': item_id_to_score[item_id],
                'from_semantic': is_from_semantic,
                'from_bm25': is_from_bm25
            })
            
            if is_from_semantic and not is_from_bm25:
                semantic_count += 1
            elif is_from_bm25 and not is_from_semantic:
                bm25_count += 1
            else:  # it's in both
                semantic_count += 0.5
                bm25_count += 0.5

        except Exception as e:
            print(f"Warning: Error processing item {item_id}: {str(e)}")
            continue

    return final_results, semantic_count, bm25_count

def retrieve_rerank(query: str, db, es_bm25, k: int) -> List[Dict[str, Any]]:
    co = cohere.Client(os.getenv("COHERE_API_KEY"))
    
    # Retrieve more results than we normally would
    results, semantic_count, bm25_count = retrieve_advanced(query, db, es_bm25, k*10)
    
    # Extract documents for reranking
    documents = [chunk_to_content(res) for res in results]

    response = co.rerank(
        model="rerank-english-v3.0",
        query=query,
        documents=documents,
        top_n=k
    )
    time.sleep(0.1)
    
    final_results = []
    for r in response.results:
        original_result = results[r.index]
        final_results.append({
            "item": original_result['item'],
            "content_type": original_result['content_type'],
            "score": r.relevance_score,
            "from_semantic": original_result['from_semantic'],
            "from_bm25": original_result['from_bm25']
        })
    
    return final_results

def main(query: str = None, load_data: bool = False):
    """
    Main function to search or load data into the vector database
    Args:
        query: The search query string (optional)
        load_data: If True, load new data into DB. If False, use existing DB
    Returns:
        List of search results if query is provided
    """
    if load_data:
        with open("/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/documents.json", "r") as f:
            dataset = json.load(f)
        vector_db = ContextualVectorDB("base_db")
        vector_db.load_data(dataset)
        
        # Write content and contextualized content to context.json
        context_data = []
        for item in vector_db.metadata:
            context_entry = {
                "doc_id": item["doc_id"]
            }
            
            if "chunk_id" in item:  # Text content
                context_entry.update({
                    "type": "text",
                    "content": item["original_content"],
                    "contextualized_content": item["contextualized_content"],
                    "chunk_id": item["chunk_id"]
                })
            else:  # Image content
                context_entry.update({
                    "type": "image",
                    "image_id": item["image_id"],
                    "path": item["path"],
                    "contextualized_content": item["contextualized_content"]
                })
            
            context_data.append(context_entry)
            
        with open("/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/context.json", "w") as f:
            json.dump(context_data, f, indent=4)
        print("Context data saved to context.json")
    
    if query:
        vector_db = ContextualVectorDB("base_db")
        vector_db.load_db()
        
        es_bm25 = create_elasticsearch_bm25_index(vector_db)
        results = retrieve_rerank(query, vector_db, es_bm25, 10)
        
        # Write results to a json file
        with open("/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/results.json", "w") as f:
            json.dump(results, f, indent=4)
        # save images to a folder
        
        
        return results

# Keep this for direct script execution, but use the new main function
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search the vector database")    
    parser.add_argument("--load_data", action="store_true", help="Load data from json file and save to new vector database")
    parser.add_argument("--query", type=str, help="Search query", default="give me the schematic diagram of a PTAT voltage generator")
    args = parser.parse_args()
    
    main(query=args.query, load_data=args.load_data)
        

