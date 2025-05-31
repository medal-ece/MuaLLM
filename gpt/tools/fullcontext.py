# use the full content of the pdf to answer the question

import anthropic
import os
from dotenv import load_dotenv
from openai import OpenAI
import sys
import json
import time
import argparse
import PyPDF2
load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))



def extract_text_from_pdf(pdf_path):
    try:
        text = ""
        with open(pdf_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    except FileNotFoundError:
        print(f"Error: PDF file not found at {pdf_path}")
        return None
    except Exception as e:
        print(f"Error reading PDF: {str(e)}")
        return None

def cag_openai(context, question):
    if context is None:
        return "Error: Could not read PDF content"
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "This is the context: " + context + "\n\n" + "This is the user query: " + question}]
    )
    
    return response.choices[0].message.content

def main(input_str, pdf_path):
    context = extract_text_from_pdf(pdf_path)
    question = input_str
    return cag_openai(context, question)

if __name__ == "__main__":
    input_str = "What is the title of the document?"
    pdf_path = "../finalAgent_db/papers/paper1.pdf"
    main(input_str, pdf_path)
