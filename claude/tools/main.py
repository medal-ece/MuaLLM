import os
import base64
from anthropic import Anthropic
from search import main as search_main
from pathlib import Path
import shutil

def load_image(image_path: str) -> str:
    """Load and encode image as base64"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error loading image {image_path}: {e}")
        return None

def answer_query(query: str, results, k: int = 5) -> str:
    output_dir = Path('query_results')
    
    # Clear previous query results
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # Keep track of image mappings
    image_map = {}  # Map image numbers to their paths
    
    # Separate image and text results
    image_results = [r for r in results[:k] if r['content_type'] == 'image']
    text_results = [r for r in results[:k] if r['content_type'] == 'text']
    image_contents = []
    text_contents = []

    # Process image results
    for i, result in enumerate(image_results, 1):
        if 'path' in result['item']:
            image_data = load_image(result['item']['path'])
            if image_data:
                image_map[i] = result['item']['path']  # Store mapping
                image_contents.extend([
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        }
                    },
                    {
                        "type": "text",
                        "text": f"Image {i} Description: {result['item'].get('contextualized_content', '')}\n"
                    }
                ])

    # Process text results
    for i, result in enumerate(text_results, 1):
        text = f"Text Reference {i}:\n"
        text += f"Original Content: {result['item'].get('original_content', '')}\n"
        text += f"Contextualized Content: {result['item'].get('contextualized_content', '')}\n"
        text_contents.append(text)

    # Modify the prompt to get structured response
    full_text = (
        f"Please answer this query: {query}\n\n"
        "Important instructions:\n"
        "1. Structure your response in a clear, readable format using appropriate headings and bullet points where necessary.\n"
        "2. Only reference images that are directly relevant to the query as 'Image N' and explain their significance.\n"
        "3. Do not mention irrelevant images in your response.\n"
        "4. Use both the provided text references and image content to create a comprehensive answer.\n"
        "5. Format your response with:\n"
        "   - A generated response using the provided text references and image content\n"
        "   - A conclusion that summarizes the main points and findings\n\n"
    )
    
    if text_contents:
        full_text += "Text References:\n" + "\n".join(text_contents) + "\n\n"
    
    # Create the message content
    message_content = []
    if image_contents:
        message_content.extend(image_contents)
    message_content.append({
        "type": "text",
        "text": full_text
    })
    
    # Get response from Claude
    anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = anthropic.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=1000,
        temperature=0.0,
        messages=[
            {
                "role": "user",
                "content": message_content
            }
        ]
    )
    
    response_text = response.content[0].text
    
    # Save response
    with open(output_dir / 'response.txt', 'w', encoding='utf-8') as f:
        f.write(response_text)
    
    # Analyze response to find referenced images
    referenced_images = set()
    for i in image_map.keys():
        if f"Image {i}" in response_text:
            referenced_images.add(i)
    
    # Save referenced images
    for img_num in referenced_images:
        source_path = Path(image_map[img_num])
        if source_path.exists():
            dest_path = output_dir / f'referenced_image_{img_num}{source_path.suffix}'
            shutil.copy2(source_path, dest_path)
            
            # Save image metadata
            with open(output_dir / f'image_{img_num}_context.txt', 'w', encoding='utf-8') as f:
                for result in image_results:
                    if result['item']['path'] == image_map[img_num]:
                        f.write(f"Description: {result['item'].get('contextualized_content', '')}\n")
                        break
    
    return response_text

def main():
    # Get query from user input
    print("\nEnter your query (press Enter to submit):")
    query = input("> ").strip()
    
    # Check if query is empty
    if not query:
        print("Error: Query cannot be empty")
        return
    
    print("\nProcessing query...")
    
    # Get search results from search.py
    results = search_main(query)
    
    # Get detailed answer using Claude
    answer = answer_query(query, results, k=10)
    
    print("\nQuery:", query)
    print("\nResponse:", answer)
    print("\nResults have been saved in the 'query_results' directory")
    return answer

if __name__ == "__main__":
    main()