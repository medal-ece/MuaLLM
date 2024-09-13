import os
import argparse
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from messages import system_message1

# Load environment variables
load_dotenv()
os.environ["ANTHROPIC_API_KEY"] = os.getenv('ANTHROPIC_API_KEY')

# Constants
PERSIST_DIRECTORY = "chroma_db"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Initialize LLM
llm = ChatAnthropic(model="claude-3-5-sonnet-20240620")
llm.invoke(system_message1)

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

def query_database(query_text):
    embedding = OpenAIEmbeddings()
    vectorstore = Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embedding)
    
    retriever = vectorstore.as_retriever()

    # Define a custom RAG prompt template
    template = """Answer the question based only on the following context:
    {context}

    Question: {question}

    Answer:"""
    prompt = ChatPromptTemplate.from_template(template)

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    print(f"Search keyword: {query_text}")

    def retrieve_and_debug(query):
        docs = retriever.invoke(query)
        context = format_docs(docs)
        with open("context.txt", "w") as f:
            f.write(context)
        return context

    rag_chain = (
        {"context": retrieve_and_debug, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    output = rag_chain.invoke(query_text)
    print("Final answer:")
    print(output)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build and query a RAG database from local documents.")
    parser.add_argument("--build", nargs='+', help="Build the database with the specified PDF files or directories")
    parser.add_argument("--query", type=str, help="Query the existing database")
    args = parser.parse_args()

    if args.build:
        build_database(args.build)
    elif args.query:
        query_database(args.query)
    else:
        print("Please specify either --build or --query")

