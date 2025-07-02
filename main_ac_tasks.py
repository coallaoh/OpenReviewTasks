from utils.gsheet import GSheetWithHeader
from utils.openreview import OpenReviewPapers
import logging

CONFERENCE_NAME = "ICCV2025"
CONFERENCE_INFO = {
    "ICML2025": dict(
        CONFERENCE_ID = 'ICML.cc/2025/Conference',
        RATING_EXTRACTOR = lambda review: review.content["overall_recommendation"]['value'],
        PAPER_NUMBER_EXTRACTOR = lambda paper: paper.number,
        NOTE_KEYS = {'review': 'summary', 'comment': 'comment', 'acknowledgement': 'acknowledgement', 'rebuttal': 'rebuttal'}
    ),
    "ICCV2025": dict(
        CONFERENCE_ID = 'thecvf.com/ICCV/2025/Conference',
        # RATING_EXTRACTOR = lambda review: int(review.content["preliminary_recommendation"]['value'].split(":")[0]),
        FINAL_RATING_EXTRACTOR = lambda review: int(review.content["final_recommendation"]['value'].split(":")[0]) if "final_recommendation" in review.content and "value" in review.content["final_recommendation"] else None,
        PAPER_NUMBER_EXTRACTOR = lambda paper: paper.number,
        NOTE_EXTRACTORS = {
            'review': lambda note: 'preliminary_recommendation' in note.content,
            'comment': lambda note: 'comment' in note.content,
            'rebuttal': lambda note: ('pdf' in note.content and 'abstract' not in note.content),
            'ac_letter': lambda note: ('pdf' in note.content and 'abstract' not in note.content and 'value' in note.content['confidential_comments_to_AC']),
        }
    )
}[CONFERENCE_NAME]

CACHE_ROOT = f"data/{CONFERENCE_NAME}/"
GSHEET_JSON = "inner-bridge-282608-030fbb66c110.json"
GSHEET_TITLE = f"{CONFERENCE_NAME} AC DB"
GSHEET_SHEET = "Sheet1"
INITIALIZE_SHEET = False

class OpenReviewACPapers(OpenReviewPapers):
    def get_ac_papers_list(self):
        logging.info("Starting to retrieve AC papers list")
        ac_group_id = f'{self.conference_id}/Area_Chairs'
        ac_group_list = self.openreview_client.get_group(ac_group_id).members
        if not ac_group_list:
            logging.warning(f"No AC information for {self.conference_id}.")
            return []

        profile = self.openreview_client.get_profile()
        if profile.id not in ac_group_list:
            logging.warning(f"You are not an area chair for {self.conference_id}.")
            return []

        logging.info("Retrieving submissions")
        submissions = self.openreview_client.get_notes(
            invitation=f'{self.conference_id}/-/Submission',
            details='replicated',
            limit=1000
        )
        logging.info(f"Found {len(submissions)} submissions")

        user_id = profile.id
        logging.info(f"Getting groups for user {user_id}")
        user_groups = self.openreview_client.get_groups(member=user_id)
        ac_groups = [g.id for g in user_groups if 'Area_Chairs' in g.id]
        logging.info(f"Found {len(ac_groups)} AC groups for user")

        paper_data = []
        logging.info("Processing papers assigned to AC")
        for paper in submissions:
            ac_group_id_for_paper = f'{self.conference_id}/Submission{paper.number}/Area_Chairs'
            if ac_group_id_for_paper not in paper.readers:
                logging.debug(f"Paper {paper.number} is not part of your area chair task.")
                continue

            if not any(ac_group in paper.readers for ac_group in ac_groups):
                logging.debug(f"You are not assigned to paper {paper.number} as an AC.")
                continue

            logging.debug(f"Processing paper {paper.number}")
            all_notes = self.openreview_client.get_notes(forum=paper.forum)
            invitation_str = f'{self.conference_id}/Submission{paper.number}/-/Official_Review'
            reviews = [note for note in all_notes if invitation_str in note.invitations]
            scores = [CONFERENCE_INFO['RATING_EXTRACTOR'](review) for review in reviews] if 'RATING_EXTRACTOR' in CONFERENCE_INFO else []
            
            # Extract final scores if FINAL_RATING_EXTRACTOR is available
            final_scores = []
            if 'FINAL_RATING_EXTRACTOR' in CONFERENCE_INFO:
                final_scores = [CONFERENCE_INFO['FINAL_RATING_EXTRACTOR'](review) for review in reviews]
                # Filter out None values for average calculation
                final_scores_filtered = [score for score in final_scores if score is not None]
            else:
                final_scores_filtered = []

            forum_notes = self.openreview_client.get_notes(forum=paper.forum)
            participating_reviewers = [note.signatures[0] for note in forum_notes if 'comment' in note.content]

            note_counts = {note_key + '_count': 0 for note_key in CONFERENCE_INFO['NOTE_EXTRACTORS'].keys()}
            for note in forum_notes:
                for key, note_extractor in CONFERENCE_INFO['NOTE_EXTRACTORS'].items():
                    if note_extractor(note):
                        note_counts[key + '_count'] += 1

            paper_url = f"https://openreview.net/forum?id={paper.forum}"

            paper_data.append({
                'paper_title': paper.content['title']['value'],
                'withdrawn': 'Withdrawn' in paper.content.get('venue', {}).get('value', ''),
                'paper_number': CONFERENCE_INFO['PAPER_NUMBER_EXTRACTOR'](paper),
                'paper_url': paper_url,
                'num_reviewers': len(reviews),
                'avg_score': round(sum(scores) / len(scores), 2) if scores else 'N/A',
                'reviewer1_score': scores[0] if len(scores) >= 1 else '',
                'reviewer2_score': scores[1] if len(scores) >= 2 else '',
                'reviewer3_score': scores[2] if len(scores) >= 3 else '',
                'reviewer4_score': scores[3] if len(scores) >= 4 else '',
                'reviewer5_score': scores[4] if len(scores) >= 5 else '',
                'avg_final_score': round(sum(final_scores_filtered) / len(final_scores_filtered), 2) if final_scores_filtered else 'N/A',
                'reviewer1_final_score': final_scores[0] if len(final_scores) >= 1 else '',
                'reviewer2_final_score': final_scores[1] if len(final_scores) >= 2 else '',
                'reviewer3_final_score': final_scores[2] if len(final_scores) >= 3 else '',
                'reviewer4_final_score': final_scores[3] if len(final_scores) >= 4 else '',
                'reviewer5_final_score': final_scores[4] if len(final_scores) >= 5 else '',
                **note_counts,
                'reviewer_participation': len(participating_reviewers),
            })
            logging.debug(f"Added paper {paper.number} to results")

        logging.info(f"Retrieved data for {len(paper_data)} papers assigned to AC")
        return paper_data

def main():
    openreview_papers = OpenReviewACPapers(
        conference_id=CONFERENCE_INFO['CONFERENCE_ID'],
    )
    ac_papers_list = openreview_papers.get_ac_papers_list()

    gsheet_write = GSheetWithHeader(key_file=GSHEET_JSON, doc_name=GSHEET_TITLE, sheet_name=GSHEET_SHEET)
    gsheet_write.write_rows(rows=ac_papers_list,
                            empty_sheet=INITIALIZE_SHEET,
                            headers=ac_papers_list[0].keys() if ac_papers_list else [],
                            index_col=None if INITIALIZE_SHEET else 'paper_number',
                            write_headers=True,
                            overwrite_headers=INITIALIZE_SHEET,
                            start_row_idx=0,
                            batch_size=1000)


if __name__ == "__main__":
    main()
