import json
import os
from main import query
import argparse
from datetime import datetime
import shutil

def process_queries(queries_file: str, output_dir: str):
    """
    Process multiple queries and store results with their answers and image paths together
    
    Expected JSON format:
    {
        "queries": [
            {
                "paper": "Paper Title",
                "questions": ["query1", "query2", ...]
            },
            ...
        ]
    }
    """
    # Create timestamp for unique run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(output_dir, f"run_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)

    # Load queries
    with open(queries_file, 'r') as f:
        query_data = json.load(f)

    all_results = []
    
    # Process each paper and its queries
    for paper_queries in query_data["queries"]:
        paper_title = paper_queries["paper"]
        
        for question in paper_queries["questions"]:
            # Construct full query
            full_query = f"{question} in {paper_title}"
            print(f"\nProcessing query: {full_query}")
            
            # Create directory for this query's images
            query_dir = os.path.join(run_dir, f"query_{len(all_results)}_images")
            os.makedirs(query_dir, exist_ok=True)
            
            # Run query and capture the answer
            response = query(full_query)
            
            # Move and record image paths if they exist
            image_paths = []
            if os.path.exists("output_images"):
                for img in os.listdir("output_images"):
                    src_path = os.path.join("output_images", img)
                    dst_path = os.path.join(query_dir, img)
                    shutil.move(src_path, dst_path)
                    image_paths.append(dst_path)
                os.rmdir("output_images")
            
            # Store result with query, answer, and image paths
            result = {
                "paper": paper_title,
                "query": question,
                "answer": response,
                "image_paths": image_paths
            }
            all_results.append(result)

    # Save all results in a single file
    results_file = os.path.join(run_dir, "final_query_results.json")
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "results": all_results
        }, f, indent=2)

    print(f"\nProcessing complete. Results saved in: {results_file}")
    return results_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process multiple queries and store results with answers")
    parser.add_argument(
        "--queries", 
        type=str, 
        default="queries.json",
        help="Path to JSON file containing queries"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="final_query_results",
        help="Output directory for results"
    )
    
    args = parser.parse_args()
    process_queries(args.queries, args.output)
