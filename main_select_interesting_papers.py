import os
import json
import random
import re

import openreview
from picklecachefunc import check_cache
import tqdm

from utils.chatbots import chatgpt
from utils.openreview import OpenReviewPapers
from utils.gsheet import GSheetWithHeader


CACHE_ROOT = "data/ICLR2025_NAVER_CANDIDATES"
CONFERENCE_ID = 'ICLR.cc/2025/Conference'
KEYWORDS = ["LLM", "VLM", "Security", "Black box", "Foundational models", "Reverse-engineering", "Safety", "Multimodal", "Vision-language",
            "Audit", "Privacy", "Agent", "Reasoning", "Tool", "Human", "RLHF", "RL", "Reinforcement learning", "Reinforcement learning from human feedback"]

GSHEET_JSON = "inner-bridge-282608-030fbb66c110.json"
GSHEET_TITLE = "ICLR 2025 people to meet"
GSHEET_SHEET = "Sheet1"
BATCH_SIZE = 100

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

SYSTEM_MESSAGE_SENIORITY = (
    "You are a knowledgeable AI Assistant tasked with inferring the seniority level of an individual as of 2024. "
    "You are provided with a structured list of experiences and past activities. "
    "Based on this information, determine the person's current seniority level. "
    "Possible seniority levels include: Masters student, PhD student, Postdoc, Research scientist, Industrial researcher, Professor, Principal investigator, Group leader, etc. "
    "If applicable, please specify the year within each program (e.g., PhD student, 4th year). "
    "Your response should be concise and directly reflect the inferred seniority level, e.g., 'Assistant Professor'."
)


class OpenReviewPapersConference(OpenReviewPapers):
    @check_cache(arg_name='file_name', create_dirs=True, override=False)
    def process_one_paper(self, submission, file_name):
        data = {
            "id": submission.id,
            "title": submission.content['title']['value'],
            "abstract": submission.content['abstract']['value'],
            "authors": [],
        }
        try:
            author_profiles = openreview.tools.get_profiles(self.openreview_client,
                                                            submission.content['authorids']['value'])
            for author_profile in author_profiles:
                author_data = {
                    "email": author_profile.content.get("preferredEmail", "N/A"),
                    "first_name": author_profile.content["names"][0].get("first", "N/A"),
                    "last_name": author_profile.content["names"][0].get("last", "N/A"),
                    "history": author_profile.content.get("history", "N/A")
                }
                
                data["authors"].append(author_data)

        except KeyError:
            print("Author info unavailable.")
            return data

        return data

    def get_papers_list(self, cache_root):
        submissions = self.openreview_client.get_all_notes(content={'venueid': self.conference_id})
        if DEBUG:
            submissions = submissions[:5]  # Process only a smaller number of papers if DEBUG is True
        data_list = []
        for submission in tqdm.tqdm(submissions):
            file_name = os.path.join(cache_root, f"{submission.id}.pkl")
            data_list.append(
                self.process_one_paper(submission, file_name=file_name)
            )
        return data_list

def check_relevance(data, cache_name):
    response_str = chatgpt(
        system_prompt=SYSTEM_MESSAGE_RELEVANCE,
        user_prompts=[f"Context paper to analyze: \n###\n{data['title']}\n###\n. \n###\n{data['abstract']}\n###\n."],
        file_name=cache_name
    )[0]
    
    # Handle the case where response_str is in the format with ```json
    if response_str.startswith('```json'):
        response_str = response_str.strip('```json\n').strip('```')
    
    try:
        response = json.loads(response_str)
    except json.JSONDecodeError:
        print(f"Failed to decode JSON for paper ID {data['id']}")
        return None
    
    return {"data": data, "response": response}

def check_seniority(history, cache_name):
    history_json = json.dumps(history, indent=2)
    response_str = chatgpt(
        system_prompt=SYSTEM_MESSAGE_SENIORITY,
        user_prompts=[f"Context history to analyze: \n###\n{history_json}\n###\n."],
        file_name=cache_name
    )[0]
    
    # Handle the case where response_str is in the format with ```json
    if response_str.startswith('```json'):
        response_str = response_str.strip('```json\n').strip('```')
    
    return {"history": history, "response": response_str}

def process_data_for_sheet(data):
    # Check relevance and get output
    this_output = check_relevance(
        data=data,
        cache_name=os.path.join(CACHE_ROOT, "gpt-3.5-turbo", f"{data['id']}.pkl"))
    
    # Skip if no relevance or if JSON decoding failed
    if this_output is None or not any(this_output['response'].values()):
        return None
    
    # Extract author information
    if this_output['data']['authors']:
        first_author = this_output['data']['authors'][0]
        seniority_info = check_seniority(
            history=first_author['history'],
            cache_name=os.path.join(CACHE_ROOT, "gpt-3.5-turbo", f"{data['id']}_seniority.pkl"))
        
        author_name = f"{first_author['first_name']} {first_author['last_name']}"
        email = first_author['email']
        seniority = seniority_info['response']
    else:
        author_name = "No Author Info"
        email = "No Email"
        seniority = "Unknown"
    
    # Extract categories
    categories = ",".join([key for key in this_output['response'] if this_output['response'][key]])
    
    # Prepare row
    row = {
        "Title": this_output['data']['title'],
        "Categories": categories,
        "#Categories": len(categories.split(",")),
        "Match": (
            re.search(r"Security|Safety|Black box|Audit|Privacy", categories) is not None and
            re.search(r"VLM|LLM|Multimodal|Foundational models|Vision-language|Agent|Reasoning|Tool|Human|RLHF|RL|Reinforcement learning|Reinforcement learning from human feedback", categories) is not None
        ),
        "Seniority": seniority,
        "Author": author_name,
        "Email": email
    }
    return row

def main():
    openreview_papers = OpenReviewPapersConference(
        conference_id=CONFERENCE_ID,
    )
    data_list = openreview_papers.get_papers_list(cache_root=CACHE_ROOT)
    
    # Initialize Google Sheet writer
    gsheet_writer = GSheetWithHeader(key_file=GSHEET_JSON, doc_name=GSHEET_TITLE, sheet_name=GSHEET_SHEET)

    # Process data and prepare rows for Google Sheet
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