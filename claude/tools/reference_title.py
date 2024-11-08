import anthropic
import os
from typing import Optional
import dotenv

dotenv.load_dotenv()

def get_reference_title(content: str, ref_number: int) -> Optional[str]:
    """
    Ask Claude to find the title of a specific reference number from a paper
    """
    # Initialize client with API key as a named parameter
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    prompt = f"""
    From the following academic paper content, find the complete title of reference [{ref_number}].
    Only return the title, nothing else. If the reference is not found, return "Reference not found".

    Paper content:
    {content}
    """
    
    try:
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1024,
            temperature=0,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        return message.content[0].text.strip()
        
    except Exception as e:
        print(f"Error querying Claude: {e}")
        return None

def main():
    # Read the paper content from documents.json
    import json
    
    try:
        with open('../agent_db/documents.json', 'r') as f:
            documents = json.load(f)
            
        # Combine all chunks' content
        paper_content = documents[0]['content']
        
        # Get reference title
        ref_title = get_reference_title(paper_content, 13)
        
        if ref_title:
            print("\nReference [13] Title:")
            print(ref_title)
        else:
            print("Could not find reference title")
            
    except FileNotFoundError:
        print("Error: documents.json not found")
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in documents.json")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()