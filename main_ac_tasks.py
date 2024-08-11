from utils.gsheet import GSheetWithHeader
from utils.openreview import OpenReviewPapers

CACHE_ROOT = "data/NeurIPS2024"
CONFERENCE_ID = 'NeurIPS.cc/2024/Conference'
GSHEET_JSON = "/Users/joon/Downloads/inner-bridge-282608-046515c1295b.json"
GSHEET_TITLE = "NeurIPS2024 AC DB"
GSHEET_SHEET = "Discussion"


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
            scores = [review.content['rating']['value']
                      for review in reviews
                      if 'rating' in review.content]

            forum_notes = self.openreview_client.get_notes(forum=paper.forum)
            reviewers = [review.signatures[0] for review in reviews]

            rebuttal_exists = False
            num_participating_reviewers = 0
            for note in forum_notes:
                if "rebuttal" in note.content:
                    rebuttal_exists = True
                if ("comment" in note.content) and (note.signatures[0] in reviewers):
                    num_participating_reviewers += 1


            paper_data.append({
                'paper_title': paper.content['title']['value'],
                'withdrawn': 'Withdrawn' in paper.content.get('venue', {}).get('value', ''),
                'paper_number': paper.number,
                'num_reviewers': len(reviews),
                'avg_score': round(sum(scores) / len(scores), 2) if scores else 'N/A',
                'reviewer_scores': ','.join(map(str, sorted(scores, reverse=True))) if scores else 'N/A',
                'rebuttal?': rebuttal_exists,
                'reviewer_participation': num_participating_reviewers,
            })

        return paper_data


def main():
    openreview_papers = OpenReviewACPapers(
        conference_id=CONFERENCE_ID,
    )
    ac_papers_list = openreview_papers.get_ac_papers_list()

    gsheet_write = GSheetWithHeader(key_file=GSHEET_JSON, doc_name=GSHEET_TITLE, sheet_name=GSHEET_SHEET)
    gsheet_write.write_rows(rows=ac_papers_list,
                            headers=sorted(ac_papers_list[0].keys()),
                            empty_sheet=False,
                            write_headers=True,
                            start_row_idx=0,
                            batch_size=1000)


if __name__ == "__main__":
    main()
