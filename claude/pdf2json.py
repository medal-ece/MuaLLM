import json
import PyPDF2
import uuid
import argparse
import os

def process_pdf(pdf_path, doc_id):
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        content = ""
        chunks = []
        
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            content += page_text
            
            chunk = {
                "chunk_id": f"doc_{doc_id}_chunk_{i}",
                "original_index": i,
                "content": page_text
            }
            chunks.append(chunk)
        
        document = {
            "doc_id": f"doc_{doc_id}",
            "original_uuid": str(uuid.uuid4().hex),
            "content": content,
            "chunks": chunks
        }
        
        return document

def main():
    parser = argparse.ArgumentParser(description="Process PDF files into JSON format")
    parser.add_argument("pdf_files", nargs="+", help="PDF files to process")
    parser.add_argument("-o", "--output", default="data.json", help="Output JSON file")
    args = parser.parse_args()

    # Load existing data if the output file exists
    if os.path.exists(args.output):
        with open(args.output, 'r', encoding='utf-8') as f:
            existing_documents = json.load(f)
        start_id = max(int(doc['doc_id'].split('_')[1]) for doc in existing_documents) + 1
    else:
        existing_documents = []
        start_id = 1

    new_documents = []
    for i, pdf_file in enumerate(args.pdf_files, start=start_id):
        document = process_pdf(pdf_file, i)
        new_documents.append(document)

    # Combine existing and new documents
    all_documents = existing_documents + new_documents

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(all_documents, f, ensure_ascii=False, indent=2)

    print(f"Processed {len(new_documents)} new PDF files. Total documents: {len(all_documents)}. Output saved to {args.output}")

if __name__ == "__main__":
    main()
