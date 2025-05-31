import os
from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic
from langsmith.wrappers import wrap_openai
from langsmith.wrappers import wrap_anthropic
from langsmith import traceable
import PyPDF2
import base64
import time

load_dotenv()

# Cost per million tokens
OPENAI_INPUT_COST = 5.00  # $5.00 per 1M input tokens
OPENAI_OUTPUT_COST = 20.00  # $20.00 per 1M output tokens
CLAUDE_INPUT_COST = 3.00  # $3.00 per 1M input tokens
CLAUDE_OUTPUT_COST = 15.00  # $15.00 per 1M output tokens

openai_client = wrap_openai(OpenAI(api_key=os.getenv('OPENAI_API_KEY')))
anthropic_client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

def calculate_cost(input_tokens, output_tokens):
    input_cost = (input_tokens / 1_000_000) * OPENAI_INPUT_COST
    output_cost = (output_tokens / 1_000_000) * OPENAI_OUTPUT_COST
    total_cost = input_cost + output_cost
    return {
        'input_cost': input_cost,
        'output_cost': output_cost,
        'total_cost': total_cost,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens
    }

def calculate_claude_cost(input_tokens, output_tokens):
    input_cost = (input_tokens / 1_000_000) * CLAUDE_INPUT_COST
    output_cost = (output_tokens / 1_000_000) * CLAUDE_OUTPUT_COST
    total_cost = input_cost + output_cost
    return {
        'input_cost': input_cost,
        'output_cost': output_cost,
        'total_cost': total_cost,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens
    }

def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, "rb") as f:
        pdf_reader = PyPDF2.PdfReader(f)
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
    return text

def cag_openai(context, question):
    start_time = time.time()
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "This is the context: " + context + "\n\n" + "This is the user query: " + question}]
    )
    end_time = time.time()
    latency = end_time - start_time
    
    cost_info = calculate_cost(
        response.usage.prompt_tokens,
        response.usage.completion_tokens
    )
    cost_info['latency'] = latency
    return response.choices[0].message.content, cost_info

if __name__ == "__main__":
    print("This file has been split into data_collection.py and plot_results.py")
    print("Please run data_collection.py to collect and save the data")
    print("Then run plot_results.py to create the visualization")

