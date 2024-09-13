# RAG_research
RAG on electronic circuits


# Project Setup and Usage Guide

## How to Run the Project

### 1. Create a `papers` Directory
In the root directory of your project, create a folder named `papers` and place all the PDF files you want to test in this folder. For example:
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

### 4. Build the Database
To build the database from the PDF files in the `papers` directory, run the following command and specify the files you want to include:
```
python rag.py --build "papers/paper1.pdf" "papers/paper2.pdf" "papers/paper3.pdf" ...
```

### 5. Query the System
Once the database is built, you can query the system using one of the following commands:

- For semantic search:
  ```
  python semantic_search_anthropic.py --query "What is the equation of Voltage Reference VREF"
  ```

- For keyword-based search:
  ```
  python keyword_rag_anthropic.py --query "What is the equation of Voltage Reference VREF"
  ```
