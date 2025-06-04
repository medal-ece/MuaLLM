import json
import matplotlib.pyplot as plt

def plot_tokens_vs_cost(data):
    # Extract data from JSON
    pages_list = []
    openai_costs = []
    claude_costs = []
    muallm_gpt_cost = data[0]['muallm_gpt_cost']  # Get from first entry since it's constant
    muallm_claude_cost = data[0]['muallm_claude_cost']  # Get from first entry since it's constant
    
    for result in data:
        # Convert page count string to number (e.g., '9_pages' -> 9)
        pages = int(result['page_count'].split('_')[0])
        pages_list.append(pages)
        openai_costs.append(result['openai_total_cost'])
        claude_costs.append(result['claude_total_cost'])
    
    plt.figure(figsize=(10, 6))
    plt.plot(pages_list, openai_costs, 'b-', linewidth=2, label='GPT-4o')
    plt.plot(pages_list, claude_costs, 'g-', linewidth=2, label='Claude Sonnet 3.5')
    
    # Add MuaLLM lines using values from data
    plt.axhline(y=muallm_gpt_cost, color='r', linestyle='-', linewidth=2, label='MuaLLM GPT-4o')
    plt.axhline(y=muallm_claude_cost, color='y', linestyle='-', linewidth=2, label='MuaLLM Claude Sonnet 3.5')
    
    # Add labels and title
    plt.xlabel('Number of Pages')
    plt.ylabel('Total Cost ($) per query')
    plt.title('Pages vs Total Cost per query')
    
    # Add grid
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Add legend
    plt.legend()
    
    # Save the plot
    plt.savefig('tokens_vs_cost.png')
    plt.close()

def plot_tokens_vs_latency(data):
    # Extract data from JSON
    pages_list = []
    openai_latencies = []
    claude_latencies = []
    muallm_gpt_latencies = []
    muallm_claude_latencies = []
    
    for result in data:
        # Convert page count string to number (e.g., '9_pages' -> 9)
        pages = int(result['page_count'].split('_')[0])
        pages_list.append(pages)
        openai_latencies.append(result['openai_latency'])
        claude_latencies.append(result['claude_latency'])
        muallm_gpt_latencies.append(result['muallm_gpt_latency'])
        muallm_claude_latencies.append(result['muallm_claude_latency'])
    
    plt.figure(figsize=(10, 6))
    plt.plot(pages_list, openai_latencies, 'b-', linewidth=2, label='GPT-4o')
    plt.plot(pages_list, claude_latencies, 'g-', linewidth=2, label='Claude Sonnet 3.5')
    
    # Plot MuaLLM lines using actual values from data
    plt.plot(pages_list, muallm_gpt_latencies, 'r-', linewidth=2, label='MuaLLM GPT-4o')
    plt.plot(pages_list, muallm_claude_latencies, 'y-', linewidth=2, label='MuaLLM Claude Sonnet 3.5')
    
    # Add labels and title
    plt.xlabel('Number of Pages')
    plt.ylabel('Latency (seconds)')
    plt.title('Pages vs Latency per query')
    
    # Add grid
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Add legend
    plt.legend()
    
    # Save the plot
    plt.savefig('tokens_vs_latency.png')
    plt.close()

def main():
    # Read the JSON file
    with open('cost_analysis_results.json', 'r') as f:
        data = json.load(f)
    
    # Create the plots
    plot_tokens_vs_cost(data)
    plot_tokens_vs_latency(data)

if __name__ == "__main__":
    main() 