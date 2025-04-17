from utils.gsheet import GSheetWithHeader
from utils.openreview import OpenReviewPapers

CACHE_ROOT = "data/ICML2025"
CONFERENCE_ID = 'ICML.cc/2025/Conference'
GSHEET_JSON = "inner-bridge-282608-030fbb66c110.json"
GSHEET_TITLE = "ICML2025 AC DB"
GSHEET_SHEET = "Sheet1"
# RATING_FIELD_NAME = "rating"
RATING_FIELD_NAME = "overall_recommendation"
NOTE_KEYS = {'review': 'summary', 'comment': 'comment', 'acknowledgement': 'acknowledgement', 'rebuttal': 'rebuttal'}


class OpenReviewACPapers(OpenReviewPapers):
    def get_ac_papers_list(self):
        ac_group_id = f'{self.conference_id}/Area_Chairs'
        ac_group_list = self.openreview_client.get_group(ac_group_id).members
        if not ac_group_list:
            print(f"No AC information for {self.conference_id}.")
            return []

        profile = self.openreview_client.get_profile()
        if profile.id not in ac_group_list:
            print(f"You are not an area chair for {self.conference_id}.")
            return []

        submissions = self.openreview_client.get_notes(
            invitation=f'{self.conference_id}/-/Submission',
            details='replicated',
            limit=1000
        )

        user_id = profile.id
        user_groups = self.openreview_client.get_groups(member=user_id)
        ac_groups = [g.id for g in user_groups if 'Area_Chairs' in g.id]

        paper_data = []
        for paper in submissions:
            ac_group_id_for_paper = f'{self.conference_id}/Submission{paper.number}/Area_Chairs'
            if ac_group_id_for_paper not in paper.readers:
                print(f"Paper {paper.number} is not part of your area chair task.")
                continue

            if not any(ac_group in paper.readers for ac_group in ac_groups):
                print(f"You are not assigned to paper {paper.number} as an AC.")
                continue

            all_notes = self.openreview_client.get_notes(forum=paper.forum)
            invitation_str = f'{self.conference_id}/Submission{paper.number}/-/Official_Review'
            reviews = [note for note in all_notes if invitation_str in note.invitations]
            scores = [review.content[RATING_FIELD_NAME]['value']
                      for review in reviews
                      if RATING_FIELD_NAME in review.content]

            forum_notes = self.openreview_client.get_notes(forum=paper.forum)
            participating_reviewers = [note.signatures[0] for note in forum_notes if 'comment' in note.content]

            note_counts = {note_key + '_count': 0 for note_key in NOTE_KEYS}
            for note in forum_notes:
                for note_key in NOTE_KEYS:
                    if note_key in note.content:
                        note_counts[note_key + '_count'] += 1

            paper_url = f"https://openreview.net/forum?id={paper.forum}"

            paper_data.append({
                'paper_title': paper.content['title']['value'],
                'withdrawn': 'Withdrawn' in paper.content.get('venue', {}).get('value', ''),
                'paper_number': paper.number,
                'paper_url': paper_url,
                'num_reviewers': len(reviews),
                'avg_score': round(sum(scores) / len(scores), 2) if scores else 'N/A',
                'reviewer1_score': scores[0] if len(scores) >= 1 else '',
                'reviewer2_score': scores[1] if len(scores) >= 2 else '',
                'reviewer3_score': scores[2] if len(scores) >= 3 else '',
                'reviewer4_score': scores[3] if len(scores) >= 4 else '',
                'reviewer5_score': scores[4] if len(scores) >= 5 else '',
                **note_counts,
                'reviewer_participation': len(participating_reviewers),
            })

        return paper_data

def main():
    openreview_papers = OpenReviewACPapers(
        conference_id=CONFERENCE_ID,
    )
    ac_papers_list = openreview_papers.get_ac_papers_list()

    gsheet_write = GSheetWithHeader(key_file=GSHEET_JSON, doc_name=GSHEET_TITLE, sheet_name=GSHEET_SHEET)
    gsheet_write.write_rows(rows=ac_papers_list,
                            empty_sheet=False,
                            headers=ac_papers_list[0].keys(),
                            index_col='paper_number',
                            write_headers=True,
                            overwrite_headers=False,
                            start_row_idx=0,
                            batch_size=1000)


if __name__ == "__main__":
    main()
