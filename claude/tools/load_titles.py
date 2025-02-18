import json

def load_titles():
    """
    Load and return titles from titles.json
    Returns:
        dict: Dictionary of numbered titles
    """
    try:
        json_path = "/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/titles_small.json"
        with open(json_path, 'r') as f:
            titles = json.load(f)
        return titles
    except Exception as e:
        print(f"Error loading titles: {e}")
        return {}

# Example usage if run directly
if __name__ == "__main__":
    titles = load_titles()
    print(f"Loaded {len(titles)} titles")
    # Print first few titles as example
    for i in range(min(3, len(titles))):
        print(f"{i+1}: {titles[str(i+1)]}")
