# using prompt caching to get the title of the paper from the reference number

import anthropic
import time
import requests
from bs4 import BeautifulSoup
import os
import dotenv
import json
import argparse

dotenv.load_dotenv()

client = anthropic.Anthropic()
MODEL_NAME = "claude-3-5-sonnet-20241022"

# api call
def ask_claude(document_content, reference_number):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "<document>" + document_content + "</document>",
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": "What is the title of the reference paper " + reference_number + " in the document? Only output the title."
                }
            ]
        }
    ]
    start_time = time.time()
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=300,
        messages=messages,
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}

    )
    return response

def main():
    # get the document id from the command line
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc_id", type=str, required=True)  
    parser.add_argument("--reference_number", type=str, required=True)
    args = parser.parse_args()
    doc_id = args.doc_id
    reference_number = args.reference_number
    # get the document content from the documents.json file
    with open("../agent_db/documents.json", "r") as f:
        documents = json.load(f)
    document_content = next((doc for doc in documents if doc["doc_id"] == doc_id), None)["content"]
    response = ask_claude(document_content, reference_number)
    print(f"cached API call input tokens: {response.usage.input_tokens}")
    print(f"cached API call output tokens: {response.usage.output_tokens}")

    print("\nSummary (cached):")
    print(response.content[0].text)


if __name__ == "__main__":
    main()