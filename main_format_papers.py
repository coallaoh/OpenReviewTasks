
import os
import json
import random

import tqdm

from utils.chatbots import chatgpt
from utils.gsheet import GSheetWithHeader


CACHE_ROOT = "data/NAACL2025_NAVER_CANDIDATES"
CONFERENCE_ID = 'aclweb.org/NAACL/2025/Conference'
KEYWORDS = ["LLM", "VLM", "Security", "Black box", "Foundational models", "Reverse-engineering", "Safety", "Multimodal", "Vision-language",
            "Audit", "Privacy", "Agent", "Reasoning", "Tool", "Human", "RLHF", "RL", "Reinforcement learning", "Reinforcement learning from human feedback"]

GSHEET_JSON = "inner-bridge-282608-030fbb66c110.json"
GSHEET_TITLE = "NAACL 2025 people to meet"
GSHEET_SHEET = "Sheet1"
BATCH_SIZE = 10

DEBUG = False  # Set DEBUG to True to process only a smaller number of papers
random.seed(714)
SYSTEM_MESSAGE_RELEVANCE = (
    "You are a helpful Senior AI Research Assistant. "
    "You are responsible for thoroughly reading the provided paper details and their relevance to my research interest. "
    "You are provided with a json-structured paper. "
    "You are responsible for checking if the paper corresponds to one of the research interests for me. "
    "My research interests are as follows:\n {keyword_list} "
    "In each case the topic is relevant only if its part of the actual main focus of the paper - not just something done by the way. "
    "A good rule of thumb is that a topic is part of the main focus if the authors mention it in the context of the papers contributions. "
    "You answer with true or false for each keyword depending whether it is relevant for the paper. "
    "It is vital that you respond in a json format. Example response: \n {example_json}"
).format(keyword_list=json.dumps(KEYWORDS, indent=2),
         example_json=json.dumps({keyword: random.choice([True, False]) for keyword in KEYWORDS}, indent=2))



def get_data_list():
    # Read the papers from the file
    with open("data/NAACL2025", "r") as f:
        content = f.read()
    
    # Parse the papers
    papers = []
    lines = content.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('<li>'):
            # Start of a paper entry
            i += 1
            if i < len(lines) and '<strong>' in lines[i]:
                # Extract title
                title_line = lines[i].strip()
                title = title_line.split('<strong>')[1].split('</strong>')[0]
                
                i += 1
                
                # Extract authors
                authors_line = lines[i].strip()
                authors_text = authors_line.split('</p>')[0]
                authors = [author.strip() for author in authors_text.split(',')]
                
                # Add paper to list
                papers.append({
                    "title": title,
                    "authors": authors
                })
        i += 1
    return papers    

def check_relevance(data, cache_name):
    response_str = chatgpt(
        system_prompt=SYSTEM_MESSAGE_RELEVANCE,
        user_prompts=[f"Context paper to analyze: \n###\n{data['title']}\n###\n\n###\n."],
        file_name=cache_name
    )[0]
    
    # Handle the case where response_str is in the format with ```json
    if response_str.startswith('```json'):
        response_str = response_str.strip('```json\n').strip('```')
    
    try:
        response = json.loads(response_str)
    except json.JSONDecodeError:
        print(f"Failed to decode JSON for paper {data['title']}")
        return None
    
    return {"data": data, "response": response}

def process_data_for_sheet(data):
    # Check relevance and get output
    relevance_output = check_relevance(
        data=data,
        cache_name=os.path.join(CACHE_ROOT, "gpt-4o", f"{data['title']}.pkl"))
    
    # Skip if no relevance or if JSON decoding failed
    if relevance_output is None or not any(relevance_output['response'].values()):
        return None
    
    # Extract categories
    categories = ",".join([key for key in relevance_output['response'] if relevance_output['response'][key]])
    
    # Prepare row
    row = {
        **data,
        "Categories": categories,
        "#Categories": len(categories.split(",")),
    }
    row['authors'] = ", ".join(data['authors'])
    return row

def main():
    data_list = get_data_list()
    
    gsheet_writer = GSheetWithHeader(key_file=GSHEET_JSON, doc_name=GSHEET_TITLE, sheet_name=GSHEET_SHEET)

    rows = []
    start_row_idx = 0
    for data in tqdm.tqdm(data_list, desc="Processing papers"):
        row = process_data_for_sheet(data)
        if row:
            rows.append(row)

        # Write to Google Sheet every BATCH_SIZE rows
        if len(rows) >= BATCH_SIZE:
            headers = list(row.keys())
            gsheet_writer.write_rows(rows, empty_sheet=False, headers=headers, write_headers=(start_row_idx == 0), start_row_idx=start_row_idx)
            start_row_idx += len(rows)  # Update start_row_idx
            rows = []  # Clear rows after writing

    # Write any remaining rows to Google Sheet
    if rows:
        headers = list(row.keys())
        gsheet_writer.write_rows(rows, empty_sheet=False, headers=headers, write_headers=(start_row_idx == 0), start_row_idx=start_row_idx)


if __name__ == "__main__":
    main()
    
    
