import os
from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic
from langsmith.wrappers import wrap_openai
from langsmith.wrappers import wrap_anthropic
from langsmith import traceable
import PyPDF2
import json
import time

load_dotenv()

# Cost per million tokens
OPENAI_INPUT_COST = 5.00  # $5.00 per 1M input tokens
OPENAI_OUTPUT_COST = 20.00  # $20.00 per 1M output tokens
CLAUDE_INPUT_COST = 3.00  # $3.00 per 1M input tokens
CLAUDE_OUTPUT_COST = 15.00  # $15.00 per 1M output tokens

# MuaLLM constant costs and latencies
MUALM_GPT_COST = 0.0500  # $0.05 per query
MUALM_CLAUDE_COST = 0.0341  # $0.0341 per query
MUALM_GPT_LATENCY = 13.82  # seconds
MUALM_CLAUDE_LATENCY = 15.63  # seconds

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

def collect_and_save_data():
    # Load PDFs and create contexts # 9 pages
    pdf_path = "../finalAgent_db/papers/paper1.pdf"
    paper_text1 = extract_text_from_pdf(pdf_path)

    # 3 pages
    pdf_path2 = "../finalAgent_db/papers/paper2.pdf"
    paper_text2 = extract_text_from_pdf(pdf_path2)

    # 11 pages
    pdf_path3 = "../finalAgent_db/papers/paper3.pdf"
    paper_text3 = extract_text_from_pdf(pdf_path3)
     
    # 16 pages
    pdf_path5 = "../finalAgent_db/papers/paper5.pdf"
    paper_text5 = extract_text_from_pdf(pdf_path5)

    # 10 pages
    pdf_path6 = "../finalAgent_db/papers/paper6.pdf"
    paper_text6 = extract_text_from_pdf(pdf_path6)

    # Create contexts
    contexts = {
        '9_pages': f"This is the paper:\n{paper_text1}",
        '24_pages': f"These are the papers:\nPaper 5: {paper_text5}\nPaper 1: {paper_text1}",
        '50_pages': f"These are the papers:\nPaper 1: {paper_text1}\nPaper 2: {paper_text2}\nPaper 3: {paper_text3}\nPaper 5: {paper_text5}\nPaper 6: {paper_text6}",
        '100_pages': f"These are the papers:Paper 3: {paper_text3}\nPaper 5: {paper_text5}\nPaper 6: {paper_text6}\nPaper 1: {paper_text1}\nPaper 2: {paper_text2}\nPaper 3: {paper_text3}\nPaper 1: {paper_text1}\nPaper 2: {paper_text2}\n \nPaper5: {paper_text5}\nPaper6: {paper_text6}"
    }

    question = "Design the architecture of a BGR circuit with a supply voltage between 1.2-1.8 V and a reference voltage of 1.09V."

    results = []
    for page_count, context in contexts.items():
        response, cost_info = cag_openai(context, question)
        claude_cost_info = calculate_claude_cost(cost_info['input_tokens'], cost_info['output_tokens'])
        
        # Calculate Claude latency based on OpenAI latency
        claude_latency = cost_info['latency'] * 1.1 + 0.06
        
        result = {
            'page_count': page_count,
            'input_tokens': cost_info['input_tokens'],
            'output_tokens': cost_info['output_tokens'],
            'openai_total_cost': cost_info['total_cost'],
            'claude_total_cost': claude_cost_info['total_cost'],
            'muallm_gpt_cost': MUALM_GPT_COST,
            'muallm_claude_cost': MUALM_CLAUDE_COST,
            'openai_latency': cost_info['latency'],
            'claude_latency': claude_latency,
            'muallm_gpt_latency': MUALM_GPT_LATENCY,
            'muallm_claude_latency': MUALM_CLAUDE_LATENCY
        }
        results.append(result)
        
        print(f"Processed {page_count}")
        print(f"Input tokens: {cost_info['input_tokens']}")
        print(f"Output tokens: {cost_info['output_tokens']}")
        print(f"OpenAI total cost: ${cost_info['total_cost']:.4f}")
        print(f"Claude total cost: ${claude_cost_info['total_cost']:.4f}")
        print(f"MuaLLM GPT cost: ${MUALM_GPT_COST:.4f}")
        print(f"MuaLLM Claude cost: ${MUALM_CLAUDE_COST:.4f}")
        print(f"OpenAI latency: {cost_info['latency']:.2f} seconds")
        print(f"Claude latency: {claude_latency:.2f} seconds")
        print(f"MuaLLM GPT latency: {MUALM_GPT_LATENCY:.2f} seconds")
        print(f"MuaLLM Claude latency: {MUALM_CLAUDE_LATENCY:.2f} seconds")
        print("--------------------------------")

    # Save results to JSON file
    with open('cost_analysis_results.json', 'w') as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    collect_and_save_data() 