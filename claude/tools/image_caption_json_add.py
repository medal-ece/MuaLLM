import json

# Load the context file
with open('/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent2_db/context.json', 'r') as f:
    context_data = json.load(f)

# Load the captions file
with open('/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent2_db/image_captions_paper1.json', 'r') as f:
    captions_data = json.load(f)

# Create a dictionary of image paths to captions
caption_map = {
    img['image_path']: img['caption'] 
    for img in captions_data['images']
}

# Update context entries with matching captions
for entry in context_data:
    if entry.get('type') == 'image' and entry.get('path'):
        # Extract just the image filename from the path
        context_img_name = entry['path'].split('/')[-1]
        
        # Find matching caption by checking if any caption path ends with same image name
        for caption_path, caption in caption_map.items():
            if caption_path.endswith(context_img_name):
                # Prepend the caption to existing contextualized_content
                entry['contextualized_content'] = f"Caption: {caption}. {entry['contextualized_content']}"
                break

# Save the updated context file
with open('/Users/pravallikaabbineni/Desktop/school/RAG_research/claude/agent2_db/context.json', 'w') as f:
    json.dump(context_data, f, indent=4)
