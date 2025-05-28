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
import matplotlib.pyplot as plt
import numpy as np

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

def plot_tokens_vs_cost(input_tokens_list, total_costs_list, claude_costs_list):
    # Convert tokens to pages (1400 tokens per page)
    pages_list = [tokens / 1400 for tokens in input_tokens_list]
    
    plt.figure(figsize=(10, 6))
    plt.plot(pages_list, total_costs_list, 'b-', linewidth=2, label='GPT-4o')
    plt.plot(pages_list, claude_costs_list, 'g-', linewidth=2, label='Claude Sonnet 3.5')
    
    # Add MuaLLM line
    plt.axhline(y=0.0500, color='r', linestyle='-', linewidth=2, label='MuaLLM')
    
    # Add labels and title
    plt.xlabel('Number of Pages')
    plt.ylabel('Total Cost ($)')
    plt.title('Pages vs Total Cost')
    # Add grid
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Add legend
    plt.legend()
    
    # Save the plot
    plt.savefig('tokens_vs_cost.png')
    plt.close()

if __name__ == "__main__":
 
    # 1 paper : 9 pages
    pdf_path = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/finalAgent_db/papers/paper1.pdf"
    paper_text1 = extract_text_from_pdf(pdf_path)

    # 2 papers : 4 pages
    pdf_path2 = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/finalAgent_db/papers/paper2.pdf"
    paper_text2 = extract_text_from_pdf(pdf_path2)

    # 3 papers : 11 pages
    pdf_path3 = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/finalAgent_db/papers/paper3.pdf"
    paper_text3 = extract_text_from_pdf(pdf_path3)

    # 4 papers : 8 pages
    pdf_path4 = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/finalAgent_db/papers/paper4.pdf"
    paper_text4 = extract_text_from_pdf(pdf_path4)

    # 5 papers : 10 pages
    pdf_path5 = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/finalAgent_db/papers/paper5.pdf"
    paper_text5 = extract_text_from_pdf(pdf_path5)

    # 6 papers : 16 pages
    pdf_path6 = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/finalAgent_db/papers/paper6.pdf"
    paper_text6 = extract_text_from_pdf(pdf_path6)

    # 7 papers : 9 pages
    pdf_path7 = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/finalAgent_db/papers/paper7.pdf"
    paper_text7 = extract_text_from_pdf(pdf_path7)


    # 1 paper : 9 pages
    context_9_pages = f"""
    This is the paper:
    {paper_text1}
    """
    
    # 24 pages
    context_24_pages = f"""
    These are the papers:
    Paper 1: {paper_text1}
    Paper 2: {paper_text2}
    Paper 3: {paper_text3}
    """

    # 50 pages
    context_50_pages = f"""
    These are the papers:
    Paper 1: {paper_text1}
    Paper 2: {paper_text2}
    Paper 3: {paper_text3}
    Paper 5: {paper_text5}
    Paper 6: {paper_text6}
    """

    # # 100 pages
    # context_100_pages = f"""
    # These are the papers:
    # Paper 1: {paper_text1}
    # Paper 2: {paper_text2}
    # Paper 3: {paper_text3}
    # Paper 5: {paper_text5}
    # Paper 6: {paper_text6}
    # Paper 1: {paper_text1}
    # Paper 2: {paper_text2}
    # Paper 3: {paper_text3}
    # Paper 5: {paper_text5}
    # Paper 6: {paper_text6}
    # """

    # # 200 pages
    # context_200_pages = f"""
    # These are the papers:
    # Paper 1: {paper_text1}
    # Paper 2: {paper_text2}
    # Paper 3: {paper_text3}
    # Paper 5: {paper_text5}
    # Paper 6: {paper_text6}
    # Paper 1: {paper_text1}
    # Paper 2: {paper_text2}
    # Paper 3: {paper_text3}
    # Paper 5: {paper_text5}
    # Paper 6: {paper_text6}
    # Paper 1: {paper_text1}
    # Paper 2: {paper_text2}
    # Paper 3: {paper_text3}
    # Paper 5: {paper_text5}
    # Paper 6: {paper_text6}
    # Paper 1: {paper_text1}
    # Paper 2: {paper_text2}
    # Paper 3: {paper_text3}
    # Paper 5: {paper_text5}
    # Paper 6: {paper_text6}
    # """
    

    question = "Design the architecture of a BGR circuit with a supply voltage between 1.2-1.8 V and a reference voltage of 1.09V."

    # Lists to store data for plotting
    input_tokens_list = []
    total_costs_list = []
    claude_costs_list = []

    # for 1 paper
    response, cost_info = cag_openai(context_9_pages, question)
    # print("OpenAI response for 1 paper: ", response)
    print(f"Cost breakdown for 9 pages:")
    print(f"Input tokens: {cost_info['input_tokens']}")
    print(f"Output tokens: {cost_info['output_tokens']}")
    print(f"Input cost: ${cost_info['input_cost']:.4f}")
    print(f"Output cost: ${cost_info['output_cost']:.4f}")
    print(f"Total cost: ${cost_info['total_cost']:.4f}")
    print(f"Latency: {cost_info['latency']:.2f} seconds")
    claude_cost_info = calculate_claude_cost(cost_info['input_tokens'], cost_info['output_tokens'])
    print(f"Claude Sonnet 3.5 total cost: ${claude_cost_info['total_cost']:.4f}")
    print("--------------------------------")
    input_tokens_list.append(cost_info['input_tokens'])
    total_costs_list.append(cost_info['total_cost'])
    claude_costs_list.append(claude_cost_info['total_cost'])

    # for 3 papers
    response, cost_info = cag_openai(context_24_pages, question)
    # print("OpenAI response for 3 papers: ", response)
    print(f"Cost breakdown for 24 pages:")
    print(f"Input tokens: {cost_info['input_tokens']}")
    print(f"Output tokens: {cost_info['output_tokens']}")
    print(f"Input cost: ${cost_info['input_cost']:.4f}")
    print(f"Output cost: ${cost_info['output_cost']:.4f}")
    print(f"Total cost: ${cost_info['total_cost']:.4f}")
    print(f"Latency: {cost_info['latency']:.2f} seconds")
    claude_cost_info = calculate_claude_cost(cost_info['input_tokens'], cost_info['output_tokens'])
    print(f"Claude Sonnet 3.5 total cost: ${claude_cost_info['total_cost']:.4f}")
    input_tokens_list.append(cost_info['input_tokens'])
    total_costs_list.append(cost_info['total_cost'])
    claude_costs_list.append(claude_cost_info['total_cost'])

    # for 50 pages
    response, cost_info = cag_openai(context_50_pages, question)
    # print("OpenAI response for 50 pages: ", response)
    print(f"Cost breakdown for 50 pages:")
    print(f"Input tokens: {cost_info['input_tokens']}")
    print(f"Output tokens: {cost_info['output_tokens']}")
    print(f"Input cost: ${cost_info['input_cost']:.4f}")
    claude_cost_info = calculate_claude_cost(cost_info['input_tokens'], cost_info['output_tokens'])
    print(f"Claude Sonnet 3.5 total cost: ${claude_cost_info['total_cost']:.4f}")
    input_tokens_list.append(cost_info['input_tokens'])
    total_costs_list.append(cost_info['total_cost'])
    claude_costs_list.append(claude_cost_info['total_cost'])

    # # for 100 pages
    # response, cost_info = cag_openai(context_100_pages, question)
    # # print("OpenAI response for 100 pages: ", response)
    # print(f"Cost breakdown for 100 pages:")
    # print(f"Input tokens: {cost_info['input_tokens']}")
    # print(f"Output tokens: {cost_info['output_tokens']}")
    # print(f"Input cost: ${cost_info['input_cost']:.4f}")
    # print(f"Output cost: ${cost_info['output_cost']:.4f}")
    # claude_cost_info = calculate_claude_cost(cost_info['input_tokens'], cost_info['output_tokens'])
    # print(f"Claude Sonnet 3.5 total cost: ${claude_cost_info['total_cost']:.4f}")
    # input_tokens_list.append(cost_info['input_tokens'])
    # total_costs_list.append(cost_info['total_cost'])
    # claude_costs_list.append(claude_cost_info['total_cost'])

    # # for 200 pages
    # response, cost_info = cag_openai(context_200_pages, question)
    # # print("OpenAI response for 200 pages: ", response)
    # print(f"Cost breakdown for 200 pages:")
    # print(f"Input tokens: {cost_info['input_tokens']}")
    # print(f"Output tokens: {cost_info['output_tokens']}")
    # print(f"Input cost: ${cost_info['input_cost']:.4f}")
    # claude_cost_info = calculate_claude_cost(cost_info['input_tokens'], cost_info['output_tokens'])
    # print(f"Claude Sonnet 3.5 total cost: ${claude_cost_info['total_cost']:.4f}")
    # input_tokens_list.append(cost_info['input_tokens'])
    # total_costs_list.append(cost_info['total_cost'])
    # claude_costs_list.append(claude_cost_info['total_cost'])

    # Create the plot
    plot_tokens_vs_cost(input_tokens_list, total_costs_list, claude_costs_list)

