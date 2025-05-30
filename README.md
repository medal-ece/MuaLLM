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
- `prompts_to_json/`: Directory to store python script for extracting prompts from *.docx file and write them as desired format in the JSON file

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

## Transferring prompts from *.docx file to *.JSON file

Using these files, there is no need for human resources to work on extraction of prompts from the prompt files and write them on the JSON file manually.

### 1. File Structure

The `prompts_to_json` directory includes one main file:
* `prompt_extractor.py`: Will extract the *.docx file prompts to a JSON file and the formatted version to the another JSON file.

Also, There should be one other file to get the desired output:
* `doc.docx`: The unformatted source file for prompts.

At the end of the process two more files would be on the directory:
* `extracted_queries.json`: The questions still have their #numbers in the JSON structure, which is not desired in the final resulted JSON file. Using this file, we can check if the prompts has completely transferred to the JSON file.
* `formatted_queries.json`: The final desired JSON file (Questions without numbers).

### 2. Install Dependencies
There is only one library that should be installed using this pip command:
```
pip install python-docx
```

### 3. The process description
Using these python scripts, Every paragraph (determined with new line) with "Paper Title" as the starting characters, would be consider as a new "paper" object on the JSON file. Then the program search for every paragraph starting with "P" characters and will add them as question to the the created object in the JSON file until another paragraph with "Paper Title" occurs. Then the program will create another "paper" object and the process will goes on until reading of `doc.docx` file is finished.

This process would be handled by running the `prompt_extractor.py` script whose result will be written in two JSON output files: `extracted_queries.json` & `formatted_queries.json` in the directory.

### 4. Running the script
After making sure that the `doc.docx` is in the same directory with `prompt_extractor.py`, just run the python script.

### Note:
* In the `doc.docx` file, the paper title line should start with `Paper Title:`.
* In the `doc.docx` file, the questions should start with `P<number>:` or similar formats.