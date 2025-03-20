import os

import openreview
from picklecachefunc import check_cache
import tqdm

from utils.chatbots import chatgpt
from utils.openreview import OpenReviewPapers
from utils.gsheet import GSheetWithHeader


CACHE_ROOT = "data/ICLR2025_NAVER_CANDIDATES"
CONFERENCE_ID = 'ICLR.cc/2025/Conference'

GSHEET_JSON = "inner-bridge-282608-030fbb66c110.json"
GSHEET_TITLE = "ICLR 2025 people to meet"
GSHEET_SHEET_READ = "Sheet1"
GSHEET_SHEET_WRITE = "Sheet3"
BATCH_SIZE = 100

DEBUG = False  # Set DEBUG to True to process only a smaller number of papers


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
        data_list = []
        for submission in tqdm.tqdm(submissions):
            file_name = os.path.join(cache_root, f"{submission.id}.pkl")
            data_list.append(
                self.process_one_paper(submission, file_name=file_name)
            )
        return data_list
    
    def get_author_info_for_submissions(self, submission_id):
        try:
            submission = self.openreview_client.get_note(submission_id)
        except Exception as e:
            print(f"Error retrieving submission {submission_id}: {e}")
            return
            
        try:
            if 'authorids' in submission.content:
                # Handle API v1 format
                if isinstance(submission.content['authorids'], list):
                    author_ids = submission.content['authorids']
                # Handle API v2 format
                elif 'value' in submission.content['authorids']:
                    author_ids = submission.content['authorids']['value']
        except Exception as e:
            print(f"Error extracting author IDs from submission {submission.id}: {e}")
            return
                
        if not author_ids:
            return
        
        first_author_profile = openreview.tools.get_profiles(self.openreview_client, [author_ids[0]])[0]
        if not first_author_profile:
            return
        
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
            "phd_location": phd_location
        }
        return author_data
    

def main():
    openreview_papers = OpenReviewPapersConference(
        conference_id=CONFERENCE_ID,
    )
    or_data_list = openreview_papers.get_papers_list(cache_root=CACHE_ROOT)
    or_data_dict = {}
    for data in or_data_list:
        if 'title' in data:
            or_data_dict[data['title']] = data
        else:
            print(f"Warning: Data entry missing title field: {data}")
    
    # Log the number of papers indexed
    print(f"Indexed {len(or_data_dict)} papers by title")
    
    # Initialize Google Sheet writer
    gsheet_reader = GSheetWithHeader(key_file=GSHEET_JSON, doc_name=GSHEET_TITLE, sheet_name=GSHEET_SHEET_READ)
    gsheet_writer = GSheetWithHeader(key_file=GSHEET_JSON, doc_name=GSHEET_TITLE, sheet_name=GSHEET_SHEET_WRITE)
    
    # Read existing data from Google Sheet
    gs_data_list = gsheet_reader.get_data_list()
    if DEBUG:
        gs_data_list = gs_data_list[:5]

    rows = []
    start_row_idx = 0
    for row in tqdm.tqdm(gs_data_list, desc="Processing filtered papers"):
        if int(row['#Categories']) >= 3 and row['Match'] == "TRUE":
            row['OpenReviewId'] = or_data_dict[row['Title']]['id']
            author_info = openreview_papers.get_author_info_for_submissions(row['OpenReviewId'])
            rows.append({**row, **author_info})

        # Write to Google Sheet every BATCH_SIZE rows
        if len(rows) >= BATCH_SIZE:
            headers = list(rows[0].keys())
            gsheet_writer.write_rows(rows, empty_sheet=False, headers=headers, write_headers=(start_row_idx == 0), start_row_idx=start_row_idx)
            start_row_idx += len(rows)  # Update start_row_idx
            rows = []  # Clear rows after writing

    # Write any remaining rows to Google Sheet
    if rows:
        headers = list(rows[0].keys())
        gsheet_writer.write_rows(rows, empty_sheet=False, headers=headers, write_headers=(start_row_idx == 0), start_row_idx=start_row_idx)

if __name__ == "__main__":
    main()