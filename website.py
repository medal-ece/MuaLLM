import argparse
import bs4
from langchain import hub
from langchain_chroma import Chroma
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
import openai
import os
from dotenv import load_dotenv
from messages import system_message1

# Load environment variables from .env file
load_dotenv()

# Set OpenAI API key from environment variable
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialize the OpenAI LLM model
llm = ChatOpenAI(model="gpt-4o")

messages = system_message1
llm.invoke(messages)

def main(query_text, website_url):
    # Load, chunk, and index the contents of the website
    loader = WebBaseLoader(
        web_paths=(website_url,),
    )
    docs = loader.load()

    # Split documents into chunks
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    # Create vector store from documents
    vectorstore = Chroma.from_documents(documents=splits, embedding=OpenAIEmbeddings())

    # Retrieve and generate using the relevant snippets of the website
    retriever = vectorstore.as_retriever()
    prompt = hub.pull("rlm/rag-prompt")

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    # Invoke the RAG pipeline with the query text
    output = rag_chain.invoke(query_text)
    print(output)
    vectorstore.delete_collection()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrieve and generate using RAG from a website.")
    parser.add_argument("query_text", type=str, help="The query text to generate an answer for.")
    parser.add_argument("website_url", type=str, help="The URL of the website to retrieve and generate from.")
    args = parser.parse_args()

    main(args.query_text, args.website_url)

