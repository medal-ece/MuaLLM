import argparse
from dotenv import load_dotenv
import os
import re
import json
import base64
from PIL import Image
import io
import uuid
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.retrievers.multi_vector import MultiVectorRetriever
from langchain.storage import InMemoryStore
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from system_message import system_message

load_dotenv()
DB_PATH = "./data_base"
openai_api_key = os.environ["OPENAI_API_KEY"]

def dummy_image_to_netlist(image_path):
    # This is a dummy function that simulates converting an image to a NETLIST
    return f"NETLIST representation of {image_path}"

def search_database(query):
    # This function should be implemented to search the database and return relevant circuits
    # For now, we'll return a dummy result
    return {
        "circuits": [
            {
                "image": "./data_base/images/circuit_1.jpg",
                "text": "This is a description of circuit 1...",
                "tables": [{"Component": "R1", "Value": "10k"}]
            },
            {
                "image": "./data_base/images/circuit_2.jpg",
                "text": "This is a description of circuit 2...",
                "tables": [{"Component": "C1", "Value": "100nF"}]
            }
        ]
    }

known_actions = {
    "search_database": search_database,
    "image_to_netlist": dummy_image_to_netlist,
    "analyze_context": lambda x: "Analysis complete. Ready to formulate the final answer."
}

action_re = re.compile('^Action: (\w+): (.*)$')

class Agent:
    def __init__(self, system=""):
        self.system = system
        self.messages = []
        if self.system:
            self.messages.append({"role": "system", "content": system})

    def __call__(self, message):
        self.messages.append({"role": "user", "content": message})
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        return result

    def execute(self):
        model = ChatOpenAI(temperature=0, model="gpt-4")
        completion = model.invoke(self.messages)
        return completion.content

def query(question, max_turns=10):
    i = 0
    bot = Agent(system_message)
    next_prompt = question
    while i < max_turns:
        i += 1
        result = bot(next_prompt)
        print(result)
        actions = [action_re.match(a) for a in result.split('\n') if action_re.match(a)]
        if actions:
            action, action_input = actions[0].groups()
            if action not in known_actions:
                raise Exception(f"Unknown action: {action}: {action_input}")
            print(f" -- running {action} {action_input}")
            observation = known_actions[action](action_input)
            next_prompt = f"Observation: {json.dumps(observation)}"
        else:
            return result

def setup_vectorstore():
    embedding_function = OpenAIEmbeddings()
    vectorstore = Chroma(
        collection_name="circuit_designs",
        embedding_function=embedding_function,
        persist_directory=DB_PATH,
    )
    return vectorstore

def create_multi_vector_retriever(vectorstore, circuits):
    retriever = MultiVectorRetriever(
        vectorstore=vectorstore,
        docstore=InMemoryStore(),
    )

    for circuit in circuits:
        doc_id = str(uuid.uuid4())
        retriever.vectorstore.add_documents([
            Document(page_content=circuit['text'], metadata={"doc_id": doc_id})
        ])
        retriever.docstore.mset([(doc_id, circuit)])

    return retriever

def main(input_file: str, query_text: str):
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH)

    vectorstore = setup_vectorstore()

    if input_file:
        # Process the input file and create the retriever
        with open(input_file, 'r') as f:
            circuits = json.load(f)
        retriever = create_multi_vector_retriever(vectorstore, circuits)
    else:
        print("No input file provided. Using existing database.")
        retriever = MultiVectorRetriever(
            vectorstore=vectorstore,
            docstore=InMemoryStore(),
            id_key="doc_id",
        )

    # Update the known_actions with the created retriever
    known_actions["search_database"] = lambda x: {"circuits": retriever.get_relevant_documents(x)}

    if query_text:
        result = query(query_text)
        print("\nFinal Answer:")
        print(result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to the input file", required=False)
    parser.add_argument("--query", help="Query to process", required=True)
    args = parser.parse_args()

    main(args.input, args.query)