from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import base64
from dotenv import load_dotenv
import os
import argparse

load_dotenv()

class SummaryGenerator:
    def __init__(self):
        self.chat = ChatOpenAI(model="gpt-4o", max_tokens=1024)

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def generate_summary(self, image_path):
        base64_image = self.encode_image(image_path)
        prompt = """You are an assistant tasked with summarizing images for retrieval. 
        These summaries will be embedded and used to retrieve the raw image. 
        Give a concise summary of the image that is well optimized for retrieval."""
        
        msg = self.chat.invoke(
            [
                HumanMessage(
                    content=[
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ]
                )
            ]
        )
        return msg.content

    def add_summaries(self, document):
        for image in document['images']:
            summary = self.generate_summary(image['path'])
            image['summary'] = summary
        return document
    
def main():
    parser = argparse.ArgumentParser(description="Generate summary for an image")
    parser.add_argument("-i", "--image", required=True, help="Path to the image file")
    args = parser.parse_args()
    
    if not os.path.exists(args.image):
        print(f"Error: Image file not found at {args.image}")
        return
    
    try:
        summary_generator = SummaryGenerator()
        summary = summary_generator.generate_summary(args.image)
        print(summary)
        return summary
        
    except Exception as e:
        print(f"Error generating summary: {e}")
        return None

if __name__ == "__main__":
    summary = main()