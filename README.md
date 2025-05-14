# RAG_research
RAG on electronic circuits


# Project Setup and Usage Guide

clone repository using the following command
```
git clone https://github.com/pravallika10473/RAG_research.git
```
## Project Structure

The project is organized into different directories for various models:

- `claude/`: Contains scripts for Claude models
- `gpt/`: Contains scripts for GPT models
- `papers/`: Directory to store your PDF files for testing

## How to Run the Project

### 1. Prepare Your Papers

Place all the PDF files you want to test in the `papers` directory at the root of the project. For example:

```
papers/paper1.pdf
papers/paper2.pdf
```

### 2. Install Dependencies
Install all the required dependencies by running the following command:
```
pip install -r requirements.txt
```

### 3. Set up API Keys
Create a `.env` file in the root directory and add your API keys in the following format:
```
OPENAI_API_KEY=""
LANGCHAIN_API_KEY=""
ANTHROPIC_API_KEY=""
```

### 4. Using Claude Models

To use the Claude models, navigate to the `claude` directory:

```
cd claude
```

#### Build the Database

To build the database from the PDF files in the `papers` directory, run:

```
python keyword_rag_anthropic.py --build ../papers
```

This will process all PDF files in the `papers` directory.

#### Query the System

Once the database is built, you can query the system using one of the following commands:

- For semantic search:
  ```bash
  python semantic_search_anthropic.py --query "Your query here"
  ```

- For keyword-based search:
  ```bash
  python keyword_rag_anthropic.py --query "Your query here"
  ```

### 5. Using Other Models

If you want to use other models (e.g., OpenAI), navigate to their respective directories and follow similar steps for building the database and querying the system.

## Note

Make sure you're in the correct directory (e.g., `claude`) when running the scripts. The paths to the `papers` directory and other resources are relative to the script's location.

# Table Data Extractor

A flexible tool that extracts data from any table in an image and converts it into a structured JSON format using OpenAI's GPT-4 Vision API.

## Features

- Works with any table structure
- Preserves hierarchical relationships
- Handles special notations and units
- Provides table structure analysis
- Generates detailed metadata
- Robust error handling

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your OpenAI API key:
   - Create a `.env` file in the project root
   - Add your OpenAI API key:
```
OPENAI_API_KEY=your_api_key_here
```

## Usage

Run the script with:
```bash
python table_extractor.py path/to/your/table/image.jpg
```

The script will:
1. Read the input image
2. Use GPT-4 Vision to extract the table data
3. Analyze the table structure
4. Save the structured data to a JSON file named `table_data_[image_name].json`
5. Provide analysis of the table's characteristics

## Output Structure

The extracted data follows this structure:
```json
{
    "metadata": {
        "source_image": "path/to/image",
        "extraction_timestamp": "ISO-8601 timestamp",
        "model": "gpt-4-vision-preview"
    },
    "table_data": {
        // Extracted table content preserving original structure
    }
}
```

### Table Analysis

The script analyzes and reports:
- Whether the table is hierarchical
- Presence of units in the data
- Types of data present (numeric, text, etc.)
- Column and row structure

## Error Handling

The script includes robust error handling for:
- Invalid image files
- JSON parsing errors
- API response issues
- File system operations

## Requirements

- Python 3.8+
- OpenAI API key
- Dependencies listed in requirements.txt
