import os
import json
import random

import openreview
from picklecachefunc import check_cache
import pprint
import tqdm

from utils.chatbots import ChatBot
from utils.chatbots import CHATBOTMODELS
from utils.openreview import OpenReviewPapers

CACHE_ROOT = "data/ICML2024_NAVER_CANDIDATES"
CONFERENCE_ID = 'ICML.cc/2024/Conference'
CHATBOT_MODEL = CHATBOTMODELS["GPT_3_5_TURBO"]
KEYWORDS = ["LLM", "Security", "Black box", "Foundational models", "Reverse-engineering", "Extraction", "Safety"]

random.seed(714)
SYSTEM_MESSAGE = (
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
    @check_cache(arg_name='file_name')
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
                try:
                    data["authors"].append({
                        "email": author_profile.content["preferredEmail"],
                        "first_name": author_profile.content["names"][0]["first"],
                        "last_name": author_profile.content["names"][0]["last"],
                    })
                except Exception:
                    print("Author name unavailable.")

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


class ChatBotForICML2024(ChatBot):
    @check_cache(arg_name='cache_name')
    def check_relevance(self, data, cache_name):
        response, price = self.call_openai(human_message=(
            f"Context paper to analyze: "
            f"\n###\n{data['title']}\n###\n. "
            f"\n###\n{data['abstract']}\n###\n. "
        ))
        if any([response[key] for key in response]):
            pprint.pprint(data)
            print(",".join([key for key in response if response[key]]))
        else:
            pprint.pprint(data)
            print("NO RELEVANCE")
        return {"data": data, "response": response, "price": price}


def main():
    chatbot = ChatBotForICML2024(
        cache_root=CACHE_ROOT,
        openai_model=CHATBOT_MODEL,
        system_message=SYSTEM_MESSAGE,
    )
    openreview_papers = OpenReviewPapersConference(
        conference_id=CONFERENCE_ID,
    )
    data_list = openreview_papers.get_papers_list(cache_root=CACHE_ROOT)
    outputs = []
    for data in data_list:
        this_output = chatbot.check_relevance(
            data=data,
            cache_name=os.path.join(CACHE_ROOT, CHATBOT_MODEL["name"], f"{data['id']}.pkl"))
        outputs.append(this_output)

    for o in outputs:
        authors = [[a['email'], a['first_name'], a['last_name']] for a in o['data']['authors']]
        flattened_list = [item for sublist in authors for item in sublist]
        categories = [key for key in o['response'] if o['response'][key]]
        print(",".join([o['data']['title'], "|".join(categories), *flattened_list]))


if __name__ == "__main__":
    main()
