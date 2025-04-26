# use the full content of the pdf to answer the question

import anthropic
import os
from dotenv import load_dotenv
import sys
import json
import time
import argparse
load_dotenv()

def fullcontext(question: str, context: str) -> str:
    """
    Get response from Claude using full context
    
    Args:
        question (str): Question to ask
        context (str): Full context to use
    Returns:
        str: Claude's response
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    # Create the system message
    system_message = "You are a helpful assistant that answers questions based on the provided context."
    
    # Create the message with proper structure
    message = client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=1000,
        temperature=0,
        system=system_message,
        messages=[
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}"
            }
        ]
    )
    
    return message.content[0].text

def main(input_str):
    """
    Get response from Claude using full context from a specific paper
    
    Args:
        input_str (str): Combined string containing title and query separated by comma
    """
    # Split input into title and query
    try:
        title, query = input_str.split(", ", 1)
    except ValueError:
        raise ValueError("Input must be in format: 'title, query'")

    # read the pdf content from the json file
    pdf_content_path = os.path.join(os.path.dirname(__file__), "..", "agent_db", "pdf_content.json")
    with open(pdf_content_path, "r") as file:
        pdf_content = json.load(file)
    
    # Normalize the search title and all keys for comparison
    def normalize_title(text):
        return text.lower().replace('-', '').replace(' ', '').replace('"', '').strip()
    
    search_title = normalize_title(title)
    
    # Find the matching key that contains the title
    matching_key = None
    highest_match = 0
    
    for key in pdf_content.keys():
        # Normalize the key
        clean_key = normalize_title(key)
        if 'thetitleofthedocumentis' in clean_key:
            clean_key = clean_key.replace('thetitleofthedocumentis', '')
        
        # Check for exact match first
        if search_title == clean_key:
            matching_key = key
            break
        
        # Check for substring match
        if search_title in clean_key or clean_key in search_title:
            # Calculate match percentage
            match_length = len(set(search_title) & set(clean_key))
            if match_length > highest_match:
                highest_match = match_length
                matching_key = key
    
    if matching_key is None:
        print("Available titles:")
        for k in pdf_content.keys():
            print(f"- {k}")
        raise ValueError(f"No document found with title containing: {title}")
    
    print(f"Matched title: {matching_key}")  # Debug info
    
    results = fullcontext(query, pdf_content[matching_key])
    print(results)

    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search the vector database")    
    parser.add_argument("--input", type=str, help="Input in format: 'title, query'")
    args = parser.parse_args()
    
    if args.input:
        main(args.input)
    else:
        print("Please provide input in format: 'title, query'")