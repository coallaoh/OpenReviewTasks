import os
import json
import random
import logging

import openreview
from picklecachefunc import check_cache
import tqdm

from utils.chatbots import chatgpt
from utils.openreview import OpenReviewPapers
from utils.gsheet import GSheetWithHeader


# ---------------------------------------------------------------------------
# Set the conference name here for easy debugging and switching.
# Example values: "NAACL2025", "ACL2025", "ICML2025"
# ---------------------------------------------------------------------------

CONFERENCE_NAME = "ICML2025"  # <--- Set your conference here

# Research interest keywords remain global—these do not change with the
# conference selection.
KEYWORDS = [
    "LLM",
    "VLM",
    "Security",
    "Black box",
    "Foundational models",
    "Reverse-engineering",
    "Safety",
    "Multimodal",
    "Vision-language",
    "Audit",
    "Privacy",
    "Agent",
    "Reasoning",
    "Tool",
    "Human",
    "RLHF",
    "RL",
    "Reinforcement learning",
    "Reinforcement learning from human feedback",
]

GSHEET_JSON = "inner-bridge-282608-030fbb66c110.json"
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

class OpenReviewPapersConference(OpenReviewPapers):
    @check_cache(arg_name='file_name', create_dirs=True, override=False)
    def process_one_paper(self, submission, file_name):
        logging.debug(f"Processing paper ID: {submission.id}")
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
                    logging.warning(f"No author IDs found for submission {submission.id}")
                    return data
                
                first_author_profile = openreview.tools.get_profiles(self.openreview_client, [author_ids[0]])[0]
                if not first_author_profile:
                    logging.warning(f"No profile found for first author {author_ids[0]} in submission {submission.id}")
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
                                # Store alma mater for processing later
                                # For now, store institution name - will be processed individually
                                phd_location = alma_mater  # Store institution name temporarily
                    sorted_positions = sorted(positions.items(), key=lambda x: (x[0] if x[0] is not None else float('-inf')), reverse=True)
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
            logging.error(f"Error extracting author info from submission {submission.id}: {e}")
            return data

        return data
    def get_papers_list(self, cache_root):
        logging.info(f"Fetching papers for conference: {self.conference_id}")
        submissions = self.openreview_client.get_all_notes(content={'venueid': self.conference_id})
        logging.info(f"Total submissions fetched: {len(submissions)}")
        if DEBUG:
            submissions = submissions[:5]  # Process only a smaller number of papers if DEBUG is True
            logging.info(f"DEBUG mode: Only processing first {len(submissions)} submissions.")
        data_list = []
        for submission in tqdm.tqdm(submissions):
            file_name = os.path.join(cache_root, f"{submission.id}.pkl")
            data_list.append(
                self.process_one_paper(submission, file_name=file_name)
            )
        logging.info(f"Processed {len(data_list)} papers.")
        return data_list

def check_relevance(data_list, cache_root):
    """Check relevance for all papers using individual API calls."""
    logging.info(f"Checking relevance for {len(data_list)} papers using individual API calls")
    
    results = []
    for data in tqdm.tqdm(data_list, desc="Processing papers individually"):
        try:
            cache_name = os.path.join(cache_root, "gpt-4.1", f"{data['id']}.pkl")
            response_str = chatgpt(
                system_prompt=SYSTEM_MESSAGE_RELEVANCE,
                user_prompts=[f"Context paper to analyze: \n###\n{data['title']}\n###\n. \n###\n{data['abstract']}\n###\n."],
                file_name=cache_name,
                model_name="gpt-4.1"
            )[0]
            
            # Handle the case where response_str is in the format with ```json
            if response_str.startswith('```json'):
                response_str = response_str.strip('```json\n').strip('```')
            
            response = json.loads(response_str)
            results.append({"data": data, "response": response})
        except Exception as individual_error:
            logging.error(f"Failed to process paper {data['id']}: {individual_error}")
            results.append(None)
    
    return results



def clean_data_for_gsheets(data):
    """Clean data to ensure compatibility with Google Sheets API."""
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            # Skip the history field entirely as it's too complex
            if key == 'history':
                continue
            cleaned[key] = clean_data_for_gsheets(value)
        return cleaned
    elif isinstance(data, list):
        # For lists, convert to string representation or clean each item
        if all(isinstance(item, (str, int, float, bool, type(None))) for item in data):
            return data  # Simple list, keep as is
        else:
            # Complex list, convert to string or clean items
            cleaned_list = []
            for item in data:
                cleaned_item = clean_data_for_gsheets(item)
                # If the cleaned item is still complex, convert to string
                if isinstance(cleaned_item, (dict, list)):
                    cleaned_list.append(str(cleaned_item))
                else:
                    cleaned_list.append(cleaned_item)
            return cleaned_list
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data  # Simple types are fine
    else:
        # Unknown type, convert to string
        return str(data)

def process_relevance_results_for_sheet(relevance_results):
    """Process relevance results for Google Sheet."""
    logging.info(f"Processing {len(relevance_results)} relevance results for Google Sheet")
    
    rows = []
    for relevance_output in relevance_results:
        if relevance_output is None:
            continue
            
        data = relevance_output['data']
        response = relevance_output['response']
        
        # Skip if no relevance
        if not any(response.values()):
            logging.info(f"Paper ID {data['id']} is not relevant.")
            continue
        
        # Extract categories
        categories = ",".join([key for key in response if response[key]])
        
        # Prepare row
        row = {
            **data,
            "Categories": categories,
            "#Categories": len(categories.split(",")),
        }
        
        # Flatten authors data for better Google Sheets compatibility
        if 'authors' in row and row['authors']:
            # Take the first author (usually the main contact)
            first_author = row['authors'][0] if row['authors'] else {}
            
            # Add author fields as separate columns
            row['author_email'] = first_author.get('email', 'N/A')
            row['author_first_name'] = first_author.get('first_name', 'N/A')
            row['author_last_name'] = first_author.get('last_name', 'N/A')
            row['author_homepage'] = first_author.get('homepage', 'N/A')
            row['author_gscholar'] = first_author.get('gscholar', 'N/A')
            row['author_affiliation'] = first_author.get('affiliation', 'N/A')
            row['author_is_student'] = first_author.get('is_student', False)
            row['author_phd_location'] = first_author.get('phd_location', 'N/A')
            
            # Remove the complex authors field
            del row['authors']
        
        # Clean data thoroughly for Google Sheets compatibility
        row = clean_data_for_gsheets(row)
        
        logging.debug(f"Prepared row for paper ID {data['id']}: {row}")
        rows.append(row)
    
    return rows

def process_alma_mater_locations(data_list, cache_root):
    """Process alma mater locations for all papers using individual API calls."""
    logging.info("Processing alma mater locations individually...")
    
    # Collect all unique alma maters that need location processing
    alma_maters_to_process = set()
    for data in data_list:
        for author in data.get('authors', []):
            if author.get('is_student') and author.get('phd_location') not in ['N/A', 'Europe', 'US', 'Korea', 'Asia', 'Other']:
                alma_maters_to_process.add(author['phd_location'])
    
    if not alma_maters_to_process:
        logging.info("No alma maters to process for location.")
        return data_list
    
    alma_maters_list = list(alma_maters_to_process)
    logging.info(f"Processing {len(alma_maters_list)} unique alma maters for location.")
    
    # Process alma maters individually
    location_mapping = {}
    for alma_mater in tqdm.tqdm(alma_maters_list, desc="Processing alma maters individually"):
        try:
            cache_name = os.path.join(cache_root, "alma_mater_individual", f"{alma_mater.replace('/', '_').replace(' ', '_')}.pkl")
            response_str = chatgpt(
                system_prompt="You are a helpful assistant that can answer questions about the location of a university or institution. Choose one of the following: Europe, US, Korea, Asia, Other and return only the location.",
                user_prompts=[f"What is the location of {alma_mater}?"],
                file_name=cache_name,
                model_name="gpt-4.1"
            )[0]
            
            # Map response to standardized location
            if response_str.startswith("Europe"):
                location_mapping[alma_mater] = "Europe"
            elif response_str.startswith("US"):
                location_mapping[alma_mater] = "US"
            elif response_str.startswith("Korea"):
                location_mapping[alma_mater] = "Korea"
            elif response_str.startswith("Asia"):
                location_mapping[alma_mater] = "Asia"
            else:
                location_mapping[alma_mater] = "Other"
        except Exception as individual_error:
            logging.error(f"Failed to process alma mater {alma_mater}: {individual_error}")
            location_mapping[alma_mater] = "Other"  # Default fallback
    
    # Update data_list with processed locations
    for data in data_list:
        for author in data.get('authors', []):
            if author.get('is_student') and author.get('phd_location') in location_mapping:
                author['phd_location'] = location_mapping[author['phd_location']]
    
    logging.info("Completed alma mater location processing.")
    return data_list

# Helper utilities for conference configuration
# ---------------------------------------------------------------------------

# Lookup table for supported conferences
CONFERENCE_CONFIGS = {
    "NAACL2025": {
        "CONFERENCE_ID": "aclweb.org/NAACL/2025/Conference",
        "CACHE_ROOT": "data/NAACL2025_NAVER_CANDIDATES",
        "GSHEET_TITLE": "NAACL 2025 people to meet",
    },
    "ACL2025": {
        "CONFERENCE_ID": "aclweb.org/ACL/2025/Conference",
        "CACHE_ROOT": "data/ACL2025_NAVER_CANDIDATES",
        "GSHEET_TITLE": "ACL 2025 people to meet",
    },
    "ICML2025": {
        "CONFERENCE_ID": "ICML.cc/2025/Conference",
        "CACHE_ROOT": "data/ICML2025_NAVER_CANDIDATES",
        "GSHEET_TITLE": "ICML 2025 people to meet",
    },
    "NeurIPS2025": {
        "CONFERENCE_ID": "NeurIPS.cc/2025/Conference",
        "CACHE_ROOT": "data/NeurIPS2025_NAVER_CANDIDATES",
        "GSHEET_TITLE": "NeurIPS 2025 people to meet",
    },
    # Add more conferences as needed
}

def get_conference_config(conf_name: str):
    conf_name = conf_name.upper()
    if conf_name not in CONFERENCE_CONFIGS:
        raise ValueError(f"Conference '{conf_name}' is not in the supported conference list: {list(CONFERENCE_CONFIGS.keys())}")
    return (
        CONFERENCE_CONFIGS[conf_name]["CONFERENCE_ID"],
        CONFERENCE_CONFIGS[conf_name]["CACHE_ROOT"],
        CONFERENCE_CONFIGS[conf_name]["GSHEET_TITLE"],
    )

def main():
    logging.info("Starting script to select interesting papers.")

    try:
        conf_id, cache_root, gsheet_title = get_conference_config(CONFERENCE_NAME)
        logging.info(f"Selected conference: {CONFERENCE_NAME}")
        logging.info(f"Conference ID: {conf_id}")
        logging.info(f"Cache root: {cache_root}")
        logging.info(f"Google Sheet title: {gsheet_title}")
    except ValueError as exc:
        logging.error(f"[ERROR] {exc}")
        return

    # Ensure all helper functions that rely on the global CACHE_ROOT pick up the
    # user-selected conference.
    global CACHE_ROOT  # pylint: disable=global-variable-undefined
    CACHE_ROOT = cache_root

    # ---------------------------------------------------------------------
    # 2. Instantiate helper classes with the selected configuration.
    # ---------------------------------------------------------------------

    openreview_papers = OpenReviewPapersConference(
        conference_id=conf_id,
    )
    data_list = openreview_papers.get_papers_list(cache_root=cache_root)

    # Process alma mater locations individually
    data_list = process_alma_mater_locations(data_list, cache_root)

    # Initialize Google Sheet writer
    gsheet_writer = GSheetWithHeader(
        key_file=GSHEET_JSON, doc_name=gsheet_title, sheet_name=GSHEET_SHEET
    )

    # Process all papers for relevance checking
    logging.info("Starting relevance checking...")
    
    relevance_results = check_relevance(data_list, cache_root)
    
    # Process relevance results and prepare rows for Google Sheet
    logging.info("Processing relevance results for Google Sheet...")
    rows = process_relevance_results_for_sheet(relevance_results)
    
    # Write all rows to Google Sheet
    if rows:
        headers = list(rows[0].keys())
        logging.info(f"Headers for Google Sheet: {headers}")
        logging.info(f"Sample row data types: {[(k, type(v).__name__) for k, v in rows[0].items()]}")
        logging.info(f"Writing {len(rows)} rows to Google Sheet.")
        
        # Additional safety check - ensure no complex data types remain
        for i, row in enumerate(rows[:3]):  # Check first 3 rows
            for key, value in row.items():
                if isinstance(value, (dict, list)) and not (isinstance(value, list) and all(isinstance(item, (str, int, float, bool, type(None))) for item in value)):
                    logging.warning(f"Complex data type found in row {i}, column '{key}': {type(value)} - {value}")
        
        gsheet_writer.write_rows(
            rows,
            empty_sheet=True,  # Clear sheet first since we're writing all at once
            headers=headers,
            write_headers=True,
            start_row_idx=0,
        )
    else:
        logging.warning("No relevant papers found to write to Google Sheet.")
    logging.info("Script finished.")

if __name__ == "__main__":
    main()