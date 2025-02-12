import os
from dotenv import load_dotenv
from openai import OpenAI
import re
import httpx
import json
from messages import system_message
from search import main as search_db
from pdf2json_chunked import main as pdf2json_chunked
from fullcontext import main as full_document_search
from web_scraper import main as web_scraper
import argparse
import shutil
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Access the API key from environment variables
api_key = os.getenv('OPENAI_API_KEY')

# Initialize the OpenAI client with the API key
client = OpenAI(api_key=api_key)

class Agent:
    def __init__(self, system=""):
        self.system = system
        self.messages = []
        if self.system:
            self.messages.append({"role": "system", "content": system})

    def __call__(self, message):
        self.messages.append({"role": "user", "content": message})
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        return result

    def execute(self):
        completion = client.chat.completions.create(
                        model="gpt-4o", 
                        temperature=0,
                        messages=self.messages)
        return completion.choices[0].message.content
    
known_actions = {
    "search_db": search_db,
    "pdf2json_chunked": pdf2json_chunked,
    "full_document_search": full_document_search,
    "web_scraper": web_scraper      
}

action_re = re.compile('^Action: (\w+): (.*)$')   # python regular expression to selection action
system_message = system_message.strip()

def create_image_mapping(observation):
    """Create a mapping between figure references and actual image paths"""
    image_map = {}
    try:
        if isinstance(observation, str):
            results = json.loads(observation)
        else:
            results = observation
            
        # Extract images and create mapping
        for result in results.get('text', []):
            if result.get('content_type') == 'image':
                path = result['item'].get('path')
                if path and os.path.exists(path):
                    # Get the image filename without extension
                    filename = os.path.basename(path)
                    base_name = os.path.splitext(filename)[0]  # e.g., 'image_21'
                    
                    # Extract number from filename (e.g., '21' from 'image_21')
                    if match := re.search(r'image_(\d+)', base_name):
                        img_num = match.group(1)
                        image_map[f"Figure {img_num}"] = filename

    except Exception as e:
        print(f"Error creating image mapping: {e}")
    # print(f"Image mappings: {image_map}")
    return image_map

def extract_and_save_answer_images(answer_text, image_mappings, observation):
    """Extract and save images mentioned in the answer using image mappings"""
    try:
        # Create images directory if it doesn't exist
        output_dir = "output_images"
        os.makedirs(output_dir, exist_ok=True)
        
        # print("\nDebug: Starting image extraction")
        # print(f"Image mappings: {image_mappings}")
        
        # Find all figure references in the answer
        figure_pattern = r'Figure (\d+)'
        references = re.finditer(figure_pattern, answer_text)
        saved_images = []
        
        # Process each reference
        for ref in references:
            fig_num = ref.group(1)
            fig_ref = f"Figure {fig_num}"
            
            # print(f"Debug: Found reference to {fig_ref}")
            
            # Check if this figure exists in our mappings
            if fig_ref in image_mappings:
                filename = image_mappings[fig_ref]
                
                # Find the image in the results
                for result in observation.get('text', []):
                    if (result.get('content_type') == 'image' and 
                        'item' in result and 
                        os.path.basename(result['item'].get('path', '')) == filename):
                        
                        source_path = result['item']['path']
                        dest_path = os.path.join(output_dir, filename)
                        
                        # Copy image to output directory
                        shutil.copy2(source_path, dest_path)
                        saved_images.append((fig_ref, dest_path))
                        # print(f"Debug: Saved {fig_ref} ({filename}) to {dest_path}")
                        break
        
        # Print summary
        if saved_images:
            print(f"\nSaved images from answer:")
            # for ref, path in saved_images:
            #     print(f"- {ref} -> {path}")
            return output_dir
        else:
            print("No images found in answer")
            return None
            
    except Exception as e:
        print(f"Error saving answer images: {e}")
        return None

def query(question, max_turns=10):
    i = 0
    bot = Agent(system_message)
    next_prompt = question
    image_mappings = {}  # Store mappings between figure references and actual files
    last_observation = None  # Store the last observation for image extraction
    
    while i < max_turns:
        i += 1
        result = bot(next_prompt)
        print(result)
        
        # Check if this is the final answer (no more actions)
        if "Action:" not in result:
            # Extract and save images mentioned in the answer
            if last_observation:
                extract_and_save_answer_images(result, image_mappings, last_observation)
            return
            
        actions = [
            action_re.match(a) 
            for a in result.split('\n') 
            if action_re.match(a)
        ]
        
        if actions:
            action, action_input = actions[0].groups()
            if action not in known_actions:
                raise Exception("Unknown action: {}: {}".format(action, action_input))
            print(" -- running {} {}".format(action, action_input))
            
            # Execute action and get observation
            if action_input.startswith('(') and action_input.endswith(')'):
                try:
                    parsed_input = eval(action_input)
                    if isinstance(parsed_input, tuple):
                        observation = known_actions[action](*parsed_input)
                    else:
                        raise Exception("Expected a tuple, got: {}".format(type(parsed_input).__name__))
                except Exception as e:
                    raise Exception("Invalid action input format: {}. Error: {}".format(action_input, str(e)))
            else:
                observation = known_actions[action](action_input)
            
            # Store the observation for later image extraction
            last_observation = observation
            
            # Create mapping for this observation
            new_mappings = create_image_mapping(observation)
            image_mappings.update(new_mappings)
            
            # Add mapping information to next prompt
            if new_mappings:
                mapping_info = "\nImage mappings:\n" + "\n".join(
                    f"{ref} → {filename}" for ref, filename in new_mappings.items()
                )
                next_prompt = f"Observation: {observation}\n{mapping_info}"
            else:
                next_prompt = f"Observation: {observation}"
        else:
            
            return

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, help="Query to gpt")
    args = parser.parse_args()
    question = args.query
    query(question=question)
