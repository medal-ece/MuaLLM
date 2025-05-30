# pip install python-docx
from docx import Document
import json
import re

def extract_papers_and_questions_from_docx(docx_filepath, output_json_filepath):
    """
    Reads a .docx file, extracts paper titles and questions based on prefixes,
    and constructs a new JSON structure based on the provided format.
    """
    all_queries = [] # This will hold the list of paper objects
    current_paper_object = None

    try:
        document = Document(docx_filepath)
        print(f"Processing document: {docx_filepath}\n")

        for i, para in enumerate(document.paragraphs):
            paragraph_text = para.text.strip()

            if not paragraph_text:
                # print(f"Skipping empty paragraph at index {i}.")
                continue # Skip empty paragraphs

            # Check for "Paper Title"
            if paragraph_text.startswith("Paper Title"):
                # If there was a previous paper object, add it to the all_queries list
                if current_paper_object:
                    all_queries.append(current_paper_object)
                    print(f"--- Completed Paper: '{current_paper_object['paper']}' with {len(current_paper_object['questions'])} questions ---")

                # Create a new paper object
                paper_title = paragraph_text[len("Paper Title")+1:].strip()
                current_paper_object = {
                    "paper": paper_title,
                    "questions": []
                }
                print(f"\n--- Found new Paper Title: '{paper_title}' ---")

            # Check for "P" (as a question)
            elif paragraph_text.startswith("P") or paragraph_text.startswith("p"):
                if current_paper_object:
                    # Add "P" paragraphs as questions to the current paper
                    current_paper_object["questions"].append(paragraph_text)
                    print(f"  Added question: '{paragraph_text[:50]}...'")
                else:
                    print(f"Skipping 'P' paragraph at index {i} as no 'Paper Title' was found yet: '{paragraph_text[:50]}...'")
            else:
                print(f"Skipping paragraph at index {i} (doesn't start with 'Paper Title' or 'P'): '{paragraph_text[:50]}...'")

        # After the loop, add the last processed paper object if it exists
        if current_paper_object:
            all_queries.append(current_paper_object)
            print(f"\n--- Completed Last Paper: '{current_paper_object['paper']}' with {len(current_paper_object['questions'])} questions ---")


        # Create the final JSON structure
        final_json_data = {"queries": all_queries}

        # Write the extracted data to a new JSON file
        with open(output_json_filepath, 'w', encoding='utf-8') as f:
            json.dump(final_json_data, f, indent=4, ensure_ascii=False)
        print(f"\nExtracted data saved to: {output_json_filepath}")

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}. Please ensure '{docx_filepath}' exists.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def format_questions_in_json_file(input_json_filepath, output_json_filepath):
    """
    Reads a JSON file, removes "P<number>: " or "P<number>. " prefix from questions,
    and saves the corrected formatting to a new JSON file.

    Args:
        input_json_filepath (str): The path to the input JSON file.
        output_json_filepath (str): The path where the new formatted JSON file will be saved.
    """
    try:
        # Load the input JSON file
        with open(input_json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"Loaded data from: {input_json_filepath}")

        # Iterate through queries and format questions
        if "queries" in data and isinstance(data["queries"], list):
            for paper_obj in data["queries"]:
                if "questions" in paper_obj and isinstance(paper_obj["questions"], list):
                    formatted_questions = []
                    for question in paper_obj["questions"]:
                        # Regex to remove "P<number>:", "P<number>.", "P<number> :", "P :" etc.
                        # It handles optional spaces and different punctuation (colon or period).
                        cleaned_question = re.sub(r'^[Pp]\s*(?:\d+)?\s*[:.]\s*', '', question).strip()
                        formatted_questions.append(cleaned_question)
                    paper_obj["questions"] = formatted_questions
        
        # Save the modified data to a new JSON file
        with open(output_json_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        print(f"Formatted questions saved to: {output_json_filepath}")

    except FileNotFoundError:
        print(f"Error: The file '{input_json_filepath}' was not found. Please ensure the file exists in the correct directory.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{input_json_filepath}'. Please check its format.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# Define input and output file paths
docx_file = 'doc.docx'
extracted_prompts = 'extracted_queries.json'
final_prompts = 'formatted_queries.json'

# Call the function to process
extract_papers_and_questions_from_docx(docx_file, extracted_prompts)
format_questions_in_json_file(extracted_prompts, final_prompts)