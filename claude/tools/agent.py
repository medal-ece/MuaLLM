import os
import base64
from anthropic import Anthropic
from search import main as search_db
from pathlib import Path
import shutil
import json
import argparse
import asyncio
from pdf2json_chunked import main as pdf_process
import re
from messages import system_message
import time
from fullcontext import main as fullcontext
class Agent:
    def __init__(self, system=""):
        self.system = system
        self.messages = []
        self.image_map = {}  # Add image mapping storage
        self.output_dir = Path('query_results')

    def __call__(self, message):
        self.messages.append({"role": "user", "content": message})
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        return result

    def execute(self):
        anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        completion = anthropic.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            system=self.system,
            messages=[
                {
                    "role": m["role"],
                    "content": [{"type": "text", "text": m["content"]}] if isinstance(m["content"], str) else m["content"]
                } for m in self.messages
            ]
        )
        return completion.content[0].text
    
    def process_results(self, results, query, k=5):
        """Process search results and prepare content for Claude"""
        # Clear previous query results
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        image_results = [r for r in results[:k] if r['content_type'] == 'image']
        text_results = [r for r in results[:k] if r['content_type'] == 'text']
        image_contents = []
        text_contents = []

        # Process images
        for i, result in enumerate(image_results, 1):
            if 'path' in result['item']:
                image_data = load_image(result['item']['path'])
                if image_data:
                    self.image_map[i] = result['item']['path']
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

        # Prepare full prompt
        full_text = (
            f"Please answer this query: {query}\n\n"
            "Important instructions:\n"
            "1. Structure your response in a clear, readable format using appropriate headings and bullet points where necessary.\n"
            "2. Only reference images that are directly relevant to the query as 'Image N' and explain their significance.\n"
            "3. Don't forget to mention the images that you used in your response.\n"
            "4. Use both the provided text references and image content to create a comprehensive answer.\n"
        )
        
        if text_contents:
            full_text += "Text References:\n" + "\n".join(text_contents) + "\n\n"

        message_content = []
        if image_contents:
            message_content.extend(image_contents)
        message_content.append({
            "type": "text",
            "text": full_text
        })
        
        return message_content

    def save_response(self, response_text):
        """Save response and referenced images"""
        # Save response text
        with open(self.output_dir / 'response.txt', 'w', encoding='utf-8') as f:
            f.write(response_text)
        
        # Find and save referenced images
        referenced_images = set()
        for i in self.image_map.keys():
            if f"Image {i}" in response_text:
                referenced_images.add(i)
        
        for img_num in referenced_images:
            source_path = Path(self.image_map[img_num])
            if source_path.exists():
                dest_path = self.output_dir / f'referenced_image_{img_num}{source_path.suffix}'
                shutil.copy2(source_path, dest_path)
                
                # Save image metadata
                with open(self.output_dir / f'image_{img_num}_context.txt', 'w', encoding='utf-8') as f:
                    f.write(f"Path: {source_path}\n")

known_actions = {
    "search_db": lambda query: search_db(query=query, load_data=False),
    "load_data_and_search": lambda query: search_db(query=query, load_data=True),
    "chunk_pdf": lambda *args: pdf_process(*args), 
    "fullcontext": lambda title, query: fullcontext(title=title, query=query),    
}
action_re = re.compile(r'^Action: (\w+): (.*)$')   # Use r-prefix for raw string
system_message = system_message.strip()

def process_query(question, max_turns=10):
    #start a new result.txt file
    with open("/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/result.txt", "w") as f:
        f.write("")
    i = 0
    bot = Agent(system_message)
    next_prompt = question
    while i < max_turns:
        i += 1
        result = bot(next_prompt)
        
        with open("/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/result.txt", "a") as f:
            f.write(result)
            f.write("\n")
            f.write(next_prompt)
            
        actions = [
            action_re.match(a) 
            for a in result.split('\n') 
            if action_re.match(a)
        ]
        print(actions)
        
        if actions:
            action, action_input = actions[0].groups()
            if action not in known_actions:
                raise Exception(f"Unknown action: {action}: {action_input}")
                
            print(f" -- running {action} {action_input}")
            
            if action == "fullcontext":
                # Handle both formats: with and without parentheses
                if action_input.startswith('(') and action_input.endswith(')'):
                    # Handle tuple format
                    try:
                        parsed_input = eval(action_input)
                        observation = known_actions[action](*parsed_input)
                    except Exception as e:
                        raise Exception(f"Invalid tuple format: {str(e)}")
                else:
                    # Handle comma-separated format
                    try:
                        # Split by comma and handle quotes
                        parts = [p.strip().strip('"') for p in action_input.split('", "')]
                        if len(parts) != 2:
                            raise ValueError("Expected 2 parts: title and query")
                        title = parts[0].strip('"')
                        query = parts[1].strip('"')
                        observation = known_actions[action](title=title, query=query)
                    except Exception as e:
                        raise Exception(f"Invalid format. Expected 'title, query'. Error: {str(e)}")
            else:
                observation = known_actions[action](action_input)
                
            next_prompt = f"Observation: {observation}"
        else:
            return result

def load_image(image_path: str) -> str:
    """Load and encode image as base64"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error loading image {image_path}: {e}")
        return None

def answer_query(query: str, results, k: int = 5) -> str:
    anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    agent = Agent(system_message)
    
    # Process results and prepare content
    message_content = agent.process_results(results, query, k)
    
    # Get response from Claude
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
    
    # Save response and referenced images
    agent.save_response(response_text)
    
    return response_text

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", nargs="*", help="PDF files to process")
    parser.add_argument("--chunked", action="store_true", help="Use chunked PDF processing")
    parser.add_argument("--load_data", action="store_true", help="Load data from json file and save to new or existing vector database")
    args = parser.parse_args()
    user_query = input("> ").strip()

    # Process PDFs if specified
    if args.pdf and args.chunked:
        print("\nProcessing PDF files...")
        await pdf_process(
            pdf_files=args.pdf,
            output_path="../agent_db/documents.json",
            image_dir="../agent_db/images"
        )
        print("PDF processing complete.")

    while True:
        try:
            # First, load or update the search database if needed
            if args.load_data:
                known_actions["load_data_search"](None)
            
            # Process the query through the agent
            response = process_query(question=user_query)
            
            if response:
                print("\nFinal Response:", response)
                # save the response to a json file
                with open("/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent_db/response.txt", "w") as f:
                    f.write(str(time.time()))
                    f.write("\n")
                    f.write(user_query)
                    f.write("\n")
                    f.write(response)
                
            
        except Exception as e:
            print(f"Error processing query: {e}")
        print("\nEnter your query (or 'exit' to quit):")
        user_query = input("> ").strip()
        
        if user_query.lower() == 'exit':
            break
            
        if not user_query:
            print("Error: Query cannot be empty")
            continue
        
        print("\nProcessing query...")
        

if __name__ == "__main__":
    asyncio.run(main())