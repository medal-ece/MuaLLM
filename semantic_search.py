import argparse
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
import openai
import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate

# Load environment variables and set up OpenAI API key
load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialize the OpenAI LLM model
llm = ChatOpenAI(model="gpt-4")

# Constants
PERSIST_DIRECTORY = "semantic_search_db"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

def build_database(doc_paths):
    # Load or create the vectorstore
    embedding = OpenAIEmbeddings()
    if os.path.exists(PERSIST_DIRECTORY):
        print(f"Loading existing database from {PERSIST_DIRECTORY}")
        vectorstore = Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embedding)
    else:
        print(f"Creating new database in {PERSIST_DIRECTORY}")
        vectorstore = Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embedding)

    # Process new documents
    new_documents = []
    for doc_path in doc_paths:
        if os.path.isdir(doc_path):
            loader = DirectoryLoader(doc_path, glob="**/*.pdf", loader_cls=PyPDFLoader)
        else:
            loader = PyPDFLoader(doc_path)
        new_documents.extend(loader.load())

    if new_documents:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        splits = text_splitter.split_documents(new_documents)

        # Add new documents to the existing vectorstore
        vectorstore.add_documents(splits)
        print(f"Added {len(splits)} new document chunks to the database")
    else:
        print("No new documents to add")

    print(f"Database updated and saved to {PERSIST_DIRECTORY}")

def semantic_search(query_text, top_k=5):
    embedding = OpenAIEmbeddings()
    vectorstore = Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embedding)
    
    # Perform semantic search
    results = vectorstore.similarity_search_with_score(query_text, k=top_k)
    
    # Format and return results
    formatted_results = []
    for doc, score in results:
        formatted_results.append({
            "content": doc.page_content,
            "metadata": doc.metadata,
            "similarity_score": score
        })
    
    return formatted_results

def query_database(query_text):
    # Perform semantic search
    search_results = semantic_search(query_text)
    
    # Define a custom RAG prompt template
    template = """Answer the question based on the following context:
    {context}

    Question: {question}

    Also provide a brief explanation of how you arrived at this answer based on the given context.

    Answer:"""
    prompt = ChatPromptTemplate.from_template(template)

    def format_docs(docs):
        return "\n\n".join(f"Content: {doc['content']}\nMetadata: {doc['metadata']}\nSimilarity Score: {doc['similarity_score']}" for doc in docs)

    context = format_docs(search_results)
    
    rag_chain = (
        {"context": lambda _: context, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    output = rag_chain.invoke(query_text)
    print("Search Results:")
    for i, result in enumerate(search_results, 1):
        print(f"{i}. Similarity Score: {result['similarity_score']}")
        print(f"   Content: {result['content'][:100]}...")
        print(f"   Metadata: {result['metadata']}")
        print()
    
    print("Final answer:")
    print(output)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build and query a semantic search RAG database from local documents.")
    parser.add_argument("--build", nargs='+', help="Build the database with the specified PDF files or directories")
    parser.add_argument("--query", type=str, help="Query the existing database")
    args = parser.parse_args()

    if args.build:
        build_database(args.build)
    elif args.query:
        query_database(args.query)
    else:
        print("Please specify either --build or --query")
