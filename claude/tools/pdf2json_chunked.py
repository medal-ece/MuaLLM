import json
import uuid
import argparse
import os
from unstructured.partition.pdf import partition_pdf
import shutil
import glob
import re
import nltk
from nltk.tokenize import sent_tokenize
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
import asyncio

nltk.download('punkt', quiet=True)

class PDFProcessor:
    def __init__(self, image_dir):
        self.image_dir = image_dir
        os.makedirs(image_dir, exist_ok=True)

    def is_meaningful(self, text):
        """Filter out meaningless text"""
        cleaned_text = re.sub(r'\s', '', text)
        return len(cleaned_text) > 1 and any(char.isalnum() for char in cleaned_text)

    def create_chunks(self, text, max_chunk_size=1000, overlap=200):
        """Create overlapping chunks from text"""
        sentences = sent_tokenize(text)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_chunk_size:
                current_chunk += sentence + " "
            else:
                chunks.append(current_chunk.strip())
                current_chunk = sentence + " "
                
                # Add overlap
                overlap_text = " ".join(chunks[-1].split()[-overlap//10:])
                current_chunk = overlap_text + " " + current_chunk
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    async def process_pdf(self, pdf_path, doc_id, start_number, progress_task=None, progress=None):
        """Process PDF and extract content"""
        # Extract PDF content
        elements = partition_pdf(
            filename=pdf_path,
            extract_images_in_pdf=True,
            infer_table_structure=True,
            strategy="hi_res"
        )
        if progress_task is not None and progress is not None:
            progress.update(progress_task, advance=50)

        # Process text content
        content = ""
        chunks = []
        images = []
        chunk_id = 0

        # Extract text
        for element in elements:
            if hasattr(element, 'text'):
                element_text = element.text.strip()
                if element_text and self.is_meaningful(element_text):
                    content += element_text + "\n\n"
        
        if progress_task is not None and progress is not None:
            progress.update(progress_task, advance=20)

        # Create chunks
        text_chunks = self.create_chunks(content)
        for chunk in text_chunks:
            chunks.append({
                "chunk_id": f"doc_{doc_id}_chunk_{chunk_id}",
                "original_index": chunk_id,
                "content": chunk
            })
            chunk_id += 1

        if progress_task is not None and progress is not None:
            progress.update(progress_task, advance=20)

        # Process images
        figures_dir = os.path.join(os.getcwd(), 'figures')
        if os.path.exists(figures_dir):
            image_files = glob.glob(os.path.join(figures_dir, '*'))
            for i, image_file in enumerate(sorted(image_files), start=start_number):
                _, ext = os.path.splitext(image_file)
                new_name = f'image_{i}{ext}'
                new_path = os.path.join(self.image_dir, new_name)
                
                # Ensure relative path in JSON
                json_path = os.path.join("../agent_db/images", new_name)
                
                shutil.move(image_file, new_path)
                images.append({
                    "image_id": f"doc_{doc_id}_image_{i}",
                    "path": json_path
                })

            shutil.rmtree(figures_dir)

        if progress_task is not None and progress is not None:
            progress.update(progress_task, advance=20)

        # Create document structure
        document = {
            "doc_id": f"doc_{doc_id}",
            "original_uuid": str(uuid.uuid4().hex),
            "content": content.strip(),
            "chunks": chunks,
            "images": images
        }

        return document, len(images)

async def main():
    parser = argparse.ArgumentParser(description="Process PDF files into JSON format")
    parser.add_argument("pdf_files", nargs="+", help="PDF files to process")
    parser.add_argument("-o", "--output", default="../agent_db/documents.json", help="Output JSON file")
    parser.add_argument("-i", "--image_dir", default="../agent_db/images", help="Directory to save extracted images")
    args = parser.parse_args()

    # Load existing documents if file exists
    documents = []
    if os.path.exists(args.output):
        with open(args.output, 'r', encoding='utf-8') as f:
            try:
                documents = json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse existing {args.output}, starting fresh")

    # Get next document ID and image number
    next_doc_id = 1
    start_number = 1
    
    if documents:
        next_doc_id = max([int(doc['doc_id'].split('_')[1]) for doc in documents]) + 1
        
    # Find highest existing image number
    if os.path.exists(args.image_dir):
        existing_images = glob.glob(os.path.join(args.image_dir, 'image_*'))
        if existing_images:
            start_number = max([
                int(os.path.splitext(os.path.basename(f))[0].split('_')[1]) 
                for f in existing_images
            ]) + 1

    processor = PDFProcessor(args.image_dir)

    # Process new documents
    with Progress() as progress:
        pdf_task = progress.add_task("[cyan]Processing PDFs...", total=len(args.pdf_files))
        
        for i, pdf_file in enumerate(args.pdf_files, start=next_doc_id):
            process_task = progress.add_task(f"[cyan]Processing {os.path.basename(pdf_file)}...", total=100)
            document, num_images = await processor.process_pdf(pdf_file, i, start_number, process_task, progress)
            documents.append(document)
            start_number += num_images
            progress.update(pdf_task, advance=1)
            progress.remove_task(process_task)

    # Save output
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

    print(f"\nProcessed {len(documents)} PDF files. Output saved to {args.output}")
    print(f"Extracted images have been saved to {args.image_dir}")

if __name__ == "__main__":
    asyncio.run(main())