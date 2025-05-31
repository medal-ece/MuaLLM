import os
import json
from pathlib import Path

def combine_query_results():
    # Base directory containing all paper directories
    base_dir = Path("gpt/tools/query_results1")
    
    # Dictionary to store all results
    combined_results = {
        "papers": []
    }
    
    # Iterate through all paper directories
    for paper_dir in sorted(base_dir.glob("paper*")):
        if not paper_dir.is_dir():
            continue
            
        # Path to query_results1.json in this paper directory
        query_file = paper_dir / "query_results1.json"
        
        if not query_file.exists():
            print(f"Warning: No query_results1.json found in {paper_dir}")
            continue
            
        try:
            # Read the query results for this paper
            with open(query_file, 'r') as f:
                paper_results = json.load(f)
                
            # Add to combined results
            combined_results["papers"].append({
                "paper_directory": paper_dir.name,
                "results": paper_results["results"]
            })
            
        except Exception as e:
            print(f"Error processing {query_file}: {str(e)}")
    
    # Save combined results
    output_file = base_dir / "combined_query_results.json"
    with open(output_file, 'w') as f:
        json.dump(combined_results, f, indent=2)
    
    print(f"Combined results saved to {output_file}")

if __name__ == "__main__":
    combine_query_results() 