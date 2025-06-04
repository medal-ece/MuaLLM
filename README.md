# MuaLLM: Multimodal Large Language Model for Analog Circuit Design

## Setup and Usage

1. Clone the repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up API keys in `.env`:
```
OPENAI_API_KEY="your_openai_key"
ANTHROPIC_API_KEY="your_anthropic_key"
COHERE_API_KEY="your_cohere_key"
VOYAGE_API_KEY="your_voyage_key"
```

## Workflow

### 1. Process Papers
First, use `pdf2json_chunked.py` to process your research papers:
```bash
cd gpt/tools
python pdf2json_chunked.py --paper_path path/to/your/paper.pdf
```
This script will:
- Extract text and images from the PDF
- Chunk the text into manageable segments
- Store the processed data in a structured format

### 2. Create Multimodal Embeddings
After processing the papers, create embeddings using:
```bash
python search.py --load_data
```
This will:
- Generate embeddings for text chunks
- Create descriptive embeddings for images
- Store everything in the vector database

### 3. Query the System
To query the system:
```bash
python main.py --query "your question"
```
The agent will:
- Analyze the query type
- Select appropriate tools based on the query
- Use the hybrid RAG system to retrieve relevant information
- Generate a comprehensive response

## Notes

- Processing large PDFs may take time
- API usage may incur costs depending on your provider
