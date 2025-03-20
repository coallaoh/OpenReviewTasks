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
            if 'authorids' in submission.content:
                # Handle API v1 format
                if isinstance(submission.content['authorids'], list):
                    author_ids = submission.content['authorids']
                # Handle API v2 format
                elif 'value' in submission.content['authorids']:
                    author_ids = submission.content['authorids']['value']
                
                if not author_ids:
                    return data
                
                first_author_profile = openreview.tools.get_profiles(self.openreview_client, [author_ids[0]])[0]
                if not first_author_profile:
                    return data
                
                history = first_author_profile.content.get("history")
                is_phd_student = False
                phd_location = "N/A"
                if history:
                    positions = {}
                    for entry in history:
                        start_year = entry['start']
                        end_year = entry['end']
                        start_display = "" if start_year is None else f"{start_year-2000}"
                        end_display = "" if end_year is None else f"{end_year-2000}"
                        positions[start_year] = f"{entry['position']} @ {entry['institution']['name']} ({start_display}-{end_display})"
                        if entry['position'] == "PhD student":
                            if start_year is not None and (end_year is None or end_year >= 2025):
                                is_phd_student = True
                                alma_mater = entry['institution']['name']
                                llm_response = chatgpt(
                                    user_prompts=[f"What is the location of {alma_mater}?"],
                                    system_prompt="You are a helpful assistant that can answer questions about the location of a university or institution. Choose one of the following: Europe, US, Korea, Asia, Other and return only the location.",
                                    file_name=os.path.join(CACHE_ROOT, f"{author_ids[0]}_alma_mater_location.pkl")
                                )[0]
                                if llm_response.startswith("Europe"):
                                    phd_location = "Europe"
                                elif llm_response.startswith("US"):
                                    phd_location = "US"
                                elif llm_response.startswith("Korea"):
                                    phd_location = "Korea"
                                elif llm_response.startswith("Asia"):
                                    phd_location = "Asia"
                                else:
                                    phd_location = "Other"
                    sorted_positions = sorted(positions.items(), key=lambda x: x[0], reverse=True)
                    sorted_positions = [position for _, position in sorted_positions]
                    position_string = "\n".join(sorted_positions)
                else:
                    position_string = "N/A"
                    
                author_data = {
                    "email": first_author_profile.content.get("preferredEmail", "N/A"),
                    "homepage": first_author_profile.content.get("homepage", "N/A"),
                    "gscholar": first_author_profile.content.get("gscholar", "N/A"),
                    "first_name": first_author_profile.content["names"][0].get("first", "N/A"),
                    "last_name": first_author_profile.content["names"][0].get("last", "N/A"),
                    "affiliation": position_string,
                    "is_student": is_phd_student,
                    "phd_location": phd_location,
                    "history": history
                }
                data["authors"].append(author_data)
        except Exception as e:
            print(f"Error extracting author info from submission {submission.id}: {e}")
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

def process_data_for_sheet(data):
    # Check relevance and get output
    relevance_output = check_relevance(
        data=data,
        cache_name=os.path.join(CACHE_ROOT, "gpt-3.5-turbo", f"{data['id']}.pkl"))
    
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